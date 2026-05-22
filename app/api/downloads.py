import asyncio
import shutil
from typing import List
from pathlib import Path
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.utils import format_size, get_quality_score
from app.services.downloader import downloader_service
from app.debrid.debrid import debrid_service
from app.db.database import AsyncSessionLocal
from pydantic import BaseModel

router = APIRouter()

class DownloadRequest(BaseModel):
    urls: List[str]

@router.get("/active-downloads")
async def get_active_downloads():
    """
    Returns the list of active downloads from the downloader service.
    """
    return downloader_service.active_downloads

@router.delete("/active-downloads/{group_name}")
async def delete_active_download(group_name: str):
    """
    Removes an active download from the active list (usually to clear errors).
    """
    if group_name in downloader_service.active_downloads:
        downloader_service.active_downloads.pop(group_name, None)
        return {"status": "success"}
    return {"status": "error", "message": "Not found"}

@router.get("/downloads")
async def get_downloads():
    """
    Lists files in the download directory, filtering for video files only.
    """
    download_dir = Path(settings.DOWNLOAD_DIR)
    if not download_dir.exists():
        return []
    
    files = []
    for item in download_dir.iterdir():
        try:
            if item.is_dir():
                continue
            if item.suffix.lower() not in settings.VIDEO_EXTENSIONS:
                continue
                
            stats = item.stat()
            files.append({
                "name": item.name,
                "is_dir": item.is_dir(),
                "size": format_size(stats.st_size),
                "size_bytes": stats.st_size,
                "modified": datetime.fromtimestamp(stats.st_mtime, tz=timezone.utc).isoformat()
            })
        except FileNotFoundError:
            # File was deleted during iteration or is a broken symlink
            continue
    
    # Sort by date desc
    return sorted(files, key=lambda x: x["modified"], reverse=True)

@router.delete("/downloads/{filename}")
async def delete_download(filename: str):
    """
    Deletes a file or directory from the download directory.
    """
    path = Path(settings.DOWNLOAD_DIR) / filename
    if not path.exists():
        return {"status": "error", "message": "File not found"}
    
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.get("/downloads/file/{filename}")
async def download_file_to_pc(filename: str):
    """
    Serves a file from the download directory to the client PC.
    """
    path = Path(settings.DOWNLOAD_DIR) / filename
    
    if not path.exists():
         raise HTTPException(status_code=404, detail="File not found")
    
    if path.is_dir():
         raise HTTPException(status_code=400, detail="Cannot download a directory. Please extract it first.")
    
    try:
        path.resolve().relative_to(Path(settings.DOWNLOAD_DIR).resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")


async def run_download_task(urls: List[str], is_auto: bool = False):
    """
    Background task to unlock and download files.
    """
    client = debrid_service
    
    # 1. Unlock all links in parallel
    print(f"[API] Unlocking {len(urls)} links in parallel...")
    unlock_tasks = [client.unlock_link(url) for url in urls]
    results = await asyncio.gather(*unlock_tasks)
    
    valid_downloads = [] # List of (orig_url, unlocked_link, filename)
    for idx, res in enumerate(results):
        orig_url = urls[idx]
        if res.get("status") == "success":
            data = res.get("data", {})
            link = data.get("link")
            filename = data.get("filename")
            if link:
                valid_downloads.append((orig_url, link, filename))
        else:
            err_msg = res.get('error', 'Unknown error').strip() or "Debrid unlock failed"
            print(f"[API] Failed to unlock {orig_url}: {err_msg}")
            try:
                from app.db.models import ScrapedURL
                async with AsyncSessionLocal() as session:
                    q = await session.execute(select(ScrapedURL).where(ScrapedURL.url == orig_url))
                    existing = q.scalar_one_or_none()
                    if existing:
                        existing.status = f"failed: {err_msg[:100]}"
                        existing.last_scraped = datetime.now(timezone.utc)
                        existing.source_name = "Debrid"
                    else:
                        session.add(ScrapedURL(url=orig_url, source_name="Debrid", status=f"failed: {err_msg[:100]}"))
                    await session.commit()
            except Exception as e:
                print(f"[API] Error saving debrid error: {e}")

    if not valid_downloads:
        return

    # 3. Start downloads sequentially (one by one)
    sem = asyncio.Semaphore(1)

    async def sem_download(link, filename, category, title, year, imdb_id, season, episode, resolution, quality, language, v_quality, codec, network, audio, channels):
        async with sem:
            await downloader_service.download_file(
                link, filename, category=category, title=title, 
                year=year, is_auto=is_auto, imdb_id=imdb_id,
                season=season, episode=episode, resolution=resolution, quality=quality,
                language=language, v_quality=v_quality, codec=codec, network=network,
                audio=audio, channels=channels
            )

    # 4. Fetch metadata from DB for these URLs - Prioritize Official Metadata
    url_to_meta = {}
    async with AsyncSessionLocal() as session:
        from app.db.models import DownloadLink, MediaMetadata
        from sqlalchemy import select, func

        # Determine title priority based on default language
        if settings.DEFAULT_LANGUAGE == "fr":
            title_priority = [MediaMetadata.title_fr, MediaMetadata.official_title, DownloadLink.title, DownloadLink.filename]
        else:
            title_priority = [MediaMetadata.official_title, MediaMetadata.title_fr, DownloadLink.title, DownloadLink.filename]
        
        stmt = select(
            DownloadLink.url, 
            DownloadLink.category, 
            MediaMetadata.title_fr,
            MediaMetadata.official_title,
            DownloadLink.title,
            DownloadLink.filename,
            MediaMetadata.year,
            DownloadLink.year,
            DownloadLink.imdb_id,
            DownloadLink.season,
            DownloadLink.episode,
            DownloadLink.resolution,
            DownloadLink.quality,
            DownloadLink.language,
            DownloadLink.v_quality,
            DownloadLink.codec,
            DownloadLink.network,
            DownloadLink.audio,
            DownloadLink.channels
        ).outerjoin(
            MediaMetadata, DownloadLink.imdb_id == MediaMetadata.imdb_id
        ).where(DownloadLink.url.in_(urls))
        
        result = await session.execute(stmt)
        for row in result:
            # Robust title fallback in Python (handles None AND empty strings)
            # order: fr -> official -> ptn_title -> filename
            if settings.DEFAULT_LANGUAGE == "fr":
                title_candidates = [row.title_fr, row.official_title, row.title, row.filename]
            else:
                title_candidates = [row.official_title, row.title_fr, row.title, row.filename]
            
            final_title = next((t for t in title_candidates if t), "Unknown-Series")
            final_year = row.year or row.year_1 # SQLAlchemy suffix for double 'year' column
            
            url_to_meta[row.url.strip()] = {
                "category": row.category or "movie",
                "title": final_title,
                "year": final_year,
                "imdb_id": row.imdb_id,
                "season": row.season,
                "episode": row.episode,
                "resolution": row.resolution,
                "quality": row.quality,
                "language": row.language,
                "v_quality": row.v_quality,
                "codec": row.codec,
                "network": row.network,
                "audio": row.audio,
                "channels": row.channels
            }

    # 5. Filter for Auto-download: Skip if already downloaded with same or better quality
    filtered_downloads = []
    if is_auto:
        from app.db.models import DownloadHistory
        from sqlalchemy import and_, or_, func
        async with AsyncSessionLocal() as session:
            for orig_url, link, filename in valid_downloads:
                meta = url_to_meta.get(orig_url.strip(), {})
                title = meta.get("title")
                imdb_id = meta.get("imdb_id")
                
                # Check history
                if imdb_id:
                    h_stmt = select(DownloadHistory).where(DownloadHistory.imdb_id == imdb_id)
                else:
                    h_stmt = select(DownloadHistory).where(
                        and_(
                            DownloadHistory.year == meta.get("year"),
                            DownloadHistory.category == meta.get("category")
                        )
                    )
                
                # For series, also match season/episode
                if meta.get("category") == "series":
                    h_stmt = h_stmt.where(
                        DownloadHistory.season == meta.get("season"),
                        DownloadHistory.episode == meta.get("episode")
                    )

                h_res = await session.execute(h_stmt)
                existing = h_res.scalars().all()
                
                # If no imdb_id was matched, filter by normalized title in Python
                if not imdb_id and existing:
                    from app.core.utils import normalize_title
                    target_norm = normalize_title(title)
                    existing = [ex for ex in existing if normalize_title(ex.title) == target_norm]
                
                if existing:
                    # Check if any existing version is better or equal
                    new_score = get_quality_score(
                        meta.get("resolution"), 
                        meta.get("language"), 
                        meta.get("v_quality"), 
                        meta.get("quality"),
                        meta.get("audio")
                    )
                    is_upgrade = True
                    for ex in existing:
                        ex_score = get_quality_score(
                            ex.resolution,
                            ex.language,
                            ex.v_quality,
                            ex.quality,
                            ex.audio
                        )
                        if ex_score >= new_score:
                            is_upgrade = False
                            break
                    
                    if not is_upgrade:
                        print(f"[API] Skipping auto-download for {title}: Already have same or better quality.")
                        continue
                    else:
                        print(f"[API] Upgrade detected for {title}: {meta.get('resolution')} is better than existing.")

                # Series Pack filtering
                if not settings.AUTO_DOWNLOAD_SERIES_PACKS and meta.get("category") == "series":
                    # A pack is usually S01, S02, etc. with no specific episode
                    if meta.get("season") and not meta.get("episode"):
                        print(f"[API] Skipping auto-download for {title}: Series packs are disabled in settings.")
                        continue

                filtered_downloads.append((orig_url, link, filename))
    else:
        filtered_downloads = valid_downloads

    if not filtered_downloads:
        return

    # 2. Register only the files we are actually going to download
    downloader_service.pre_register_files([(d[1], d[2]) for d in filtered_downloads])

    print(f"[API] Starting {len(filtered_downloads)} downloads concurrently...")
    
    download_tasks = []
    for orig_url, link, filename in filtered_downloads:
        meta = url_to_meta.get(orig_url.strip(), {})
        
        download_tasks.append(sem_download(
            link, 
            filename, 
            meta.get("category", "movie"),
            meta.get("title"), 
            meta.get("year"),
            meta.get("imdb_id"),
            meta.get("season"),
            meta.get("episode"),
            meta.get("resolution"),
            meta.get("quality"),
            meta.get("language"),
            meta.get("v_quality"),
            meta.get("codec"),
            meta.get("network"),
            meta.get("audio"),
            meta.get("channels")
        ))

    await asyncio.gather(*download_tasks)

@router.post("/download")
async def trigger_download(request: DownloadRequest, background_tasks: BackgroundTasks):
    """
    Triggers download of one or more URLs via AllDebrid.
    """
    background_tasks.add_task(run_download_task, request.urls, is_auto=False)
    return {"message": f"Started download of {len(request.urls)} links in background."}

@router.get("/download-link")
async def trigger_download_get(url: str, background_tasks: BackgroundTasks):
    """
    Triggers download of one or more URLs (comma separated) via a GET request.
    Useful for RSS feeds or simple integrations.
    """
    from fastapi.responses import RedirectResponse
    urls = [u.strip() for u in url.split(",") if u.strip()]
    if not urls:
        return RedirectResponse(url="/?error=no_urls")
    
    background_tasks.add_task(run_download_task, urls, is_auto=False)
    return RedirectResponse(url="/?msg=download_started")

class CheckLinksRequest(BaseModel):
    urls: List[str]

@router.post("/check-links")
async def check_links(request: CheckLinksRequest):
    """
    Checks if a list of links is alive using the direct Hoster service.
    """
    from app.core.hoster import Hoster
    hoster = Hoster()
    result = await hoster.check_links(request.urls)
    return result
