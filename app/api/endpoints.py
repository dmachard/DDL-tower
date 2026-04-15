from fastapi import APIRouter, Depends, BackgroundTasks, Query, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, or_
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import math
import re
from pathlib import Path

from app.db.database import get_db
from app.db.models import DownloadLink, ScrapedURL, MediaMetadata
from app.core.scheduler import run_scrapers
from app.core.scanner import DirectScanner
from app.core.utils import parse_size, format_size

from app.core.config import settings
from app.services.alldebrid import AllDebridClient
from app.services.downloader import downloader_service
import asyncio
import os
import shutil
import httpx
import html

router = APIRouter(prefix="/api")

class ScanRequest(BaseModel):
    urls: List[str]

class DownloadRequest(BaseModel):
    urls: List[str]

@router.get("/config")
async def get_config():
    """
    Returns app configuration for the frontend.
    """
    return {
        "default_language": settings.DEFAULT_LANGUAGE,
        "app_name": settings.APP_NAME,
        "alldebrid_enabled": bool(settings.ALLDEBRID_API_KEY)
    }

@router.get("/active-downloads")
async def get_active_downloads():
    """
    Returns the list of active downloads from the downloader service.
    """
    return downloader_service.active_downloads

@router.get("/downloads")
async def get_downloads():
    """
    Lists files in the download directory, filtering for MKV only.
    """
    download_dir = Path(settings.DOWNLOAD_DIR)
    if not download_dir.exists():
        return []
    
    files = []
    for item in download_dir.iterdir():
        if item.is_dir():
            continue
        if item.suffix.lower() != '.mkv':
            continue
            
        stats = item.stat()
        files.append({
            "name": item.name,
            "is_dir": item.is_dir(),
            "size": format_size(stats.st_size),
            "size_bytes": stats.st_size,
            "modified": datetime.fromtimestamp(stats.st_mtime, tz=timezone.utc).isoformat()
        })
    
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
    
    # 1. Check if it exists
    if not path.exists():
         raise HTTPException(status_code=404, detail="File not found")
    
    # 2. Check if it's a directory (we don't support downloading folders directly as zip yet)
    if path.is_dir():
         raise HTTPException(status_code=400, detail="Cannot download a directory. Please extract it first.")
    
    # 3. Security: Check if path is actually inside DOWNLOAD_DIR
    try:
        path.resolve().relative_to(Path(settings.DOWNLOAD_DIR).resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    return FileResponse(path, filename=filename)

async def run_download_task(urls: List[str]):
    """
    Background task to unlock and download files.
    Processing in parallel to ensure all parts are visible in the UI right away.
    """
    client = AllDebridClient()
    
    # 1. Unlock all links in parallel
    print(f"[API] Unlocking {len(urls)} links in parallel...")
    unlock_tasks = [client.unlock_link(url) for url in urls]
    results = await asyncio.gather(*unlock_tasks)
    
    valid_downloads = []
    for res in results:
        if res.get("status") == "success":
            data = res.get("data", {})
            link = data.get("link")
            filename = data.get("filename")
            if link:
                valid_downloads.append((link, filename))
        else:
            print(f"[API] Failed to unlock a link: {res.get('error')}")

    if not valid_downloads:
        return

    # 2. Register all files before starting to ensure UI visibility and grouping
    downloader_service.pre_register_files(valid_downloads)

    # 3. Start downloads in parallel (with a limit)
    # This allows all parts to be registered in downloader_service.active_downloads immediately
    sem = asyncio.Semaphore(5) # Limit to 5 concurrent downloads

    async def sem_download(link, filename):
        async with sem:
            await downloader_service.download_file(link, filename)

    print(f"[API] Starting {len(valid_downloads)} downloads concurrently...")
    download_tasks = [sem_download(link, filename) for link, filename in valid_downloads]
    await asyncio.gather(*download_tasks)

@router.post("/download")
async def trigger_download(request: DownloadRequest, background_tasks: BackgroundTasks):
    """
    Triggers download of one or more URLs via AllDebrid.
    """
    background_tasks.add_task(run_download_task, request.urls)
    return {"message": f"Started download of {len(request.urls)} links in background."}

async def get_latest_scan_time(db: AsyncSession):
    """
    Retrieve the most recent scan timestamp from ScrapedURL table.
    """
    stmt = select(func.max(ScrapedURL.last_scraped))
    result = await db.execute(stmt)
    res = result.scalar()
    if res and res.tzinfo is None:
        return res.replace(tzinfo=timezone.utc)
    return res

async def get_threshold(db: AsyncSession, recent: bool, hours: int = None):
    """
    Unified threshold calculation for novelty window.
    """
    if not recent:
        return None
    if hours:
        return datetime.now(timezone.utc) - timedelta(hours=hours)
    
    last_scan = await get_latest_scan_time(db)
    if not last_scan:
        return None
    return last_scan - timedelta(minutes=settings.SCAN_INTERVAL_MINUTES * settings.SCAN_NOVELTY_MULTIPLIER)

@router.get("/links")
async def get_links(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    q: str = Query(None),
    category: str = Query(None),
    status: str = Query(None),
    recent: bool = Query(False),
    hours: int = Query(None)
):
    """
    Returns download links with pagination and search.
    """
    stmt = select(DownloadLink)
    
    if q:
        search_filter = or_(
            DownloadLink.filename.ilike(f"%{q}%"),
            DownloadLink.title.ilike(f"%{q}%"),
            DownloadLink.url.ilike(f"%{q}%")
        )
        stmt = stmt.where(search_filter)
    
    if category:
        stmt = stmt.where(DownloadLink.category == category)
    
    if status:
        stmt = stmt.where(DownloadLink.status == status)

    if recent:
        threshold = await get_threshold(db, recent, hours)
        if threshold:
            stmt = stmt.where(DownloadLink.last_checked >= threshold)
    
    # Get total count for pagination
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0
    
    # Get paginated items
    stmt = stmt.order_by(DownloadLink.last_checked.desc())
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    
    result = await db.execute(stmt)
    links = result.scalars().all()
    
    return {
        "items": links,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": math.ceil(total / limit) if limit > 0 else 0
    }

@router.get("/releases")
async def get_releases(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    q: str = Query(None),
    category: str = Query(None),
    source: str = Query(None),
    resolution: str = Query(None),
    year: int = Query(None),
    network: str = Query(None),
    recent: bool = Query(False),
    hours: int = Query(None)
):
    """
    Returns grouped download links (releases) for movies and series.
    """
    # Calculate novelty threshold (multiplier from config or custom hours)
    threshold = await get_threshold(db, recent, hours)

    # Base statement for groups
    stmt = select(
        func.lower(DownloadLink.title).label("lower_title"),
        func.max(DownloadLink.title).label("display_title"),
        func.max(DownloadLink.year).label("year"),
        DownloadLink.category,
        func.max(DownloadLink.last_checked).label("latest"),
        func.max(MediaMetadata.poster_path).label("poster_path"),
        func.max(MediaMetadata.plot_en).label("plot_en"),
        func.max(MediaMetadata.plot_fr).label("plot_fr"),
        func.max(MediaMetadata.rating).label("rating"),
        func.max(MediaMetadata.official_title).label("official_title"),
        func.max(MediaMetadata.title_fr).label("title_fr"),
        func.max(MediaMetadata.year).label("official_year"),
        func.coalesce(DownloadLink.imdb_id, MediaMetadata.imdb_id).label("imdb_id")
    ).where(DownloadLink.status == "alive")
    
    # Outer join with MediaMetadata
    stmt = stmt.outerjoin(MediaMetadata, DownloadLink.imdb_id == MediaMetadata.imdb_id)
    
    if q:
        stmt = stmt.where(DownloadLink.title.ilike(f"%{q}%"))
    
    if category:
        stmt = stmt.where(DownloadLink.category == category)

    if source:
        stmt = stmt.where(DownloadLink.source_name == source)

    if resolution:
        if resolution == "2160p":
            stmt = stmt.where(DownloadLink.resolution.ilike("2160p") | 
                              DownloadLink.resolution.ilike("4K") | 
                              DownloadLink.resolution.ilike("4Klight") |
                              DownloadLink.resolution.ilike("4KLIGHT"))
        else:
            stmt = stmt.where(DownloadLink.resolution == resolution)

    if year:
        stmt = stmt.where(or_(DownloadLink.year == year, MediaMetadata.year == year))

    if network:
        stmt = stmt.where(DownloadLink.network == network)

    if recent and threshold:
        stmt = stmt.where(DownloadLink.last_checked >= threshold)
        
    stmt = stmt.group_by(
        func.coalesce(DownloadLink.imdb_id, func.lower(DownloadLink.title)), 
        func.coalesce(DownloadLink.imdb_id, DownloadLink.year), 
        DownloadLink.category
    )
    
    # Get total count of groups
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0
    
    # Paginate groups
    stmt = stmt.order_by(func.max(DownloadLink.last_checked).desc())
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    
    result = await db.execute(stmt)
    groups = result.all()
    
    # For each group, fetch and aggregate its releases
    items = []
    for g_lower_title, g_title, g_year, g_cat, g_latest, g_poster, g_plot_en, g_plot_fr, g_rating, g_official, g_title_fr, g_off_year, g_imdb in groups:
        if not g_title: continue
        
        rel_stmt = select(DownloadLink).where(
            (DownloadLink.imdb_id == g_imdb if g_imdb and not g_imdb.startswith('raw') else (
                func.lower(DownloadLink.title) == g_lower_title and
                DownloadLink.year == g_year and
                DownloadLink.category == g_cat
            )),
            DownloadLink.status == "alive"
        )
        
        if source:
            rel_stmt = rel_stmt.where(DownloadLink.source_name == source)
            
        if resolution:
            if resolution == "2160p":
                rel_stmt = rel_stmt.where(DownloadLink.resolution.ilike("2160p") | 
                                          DownloadLink.resolution.ilike("4K") | 
                                          DownloadLink.resolution.ilike("4Klight") |
                                          DownloadLink.resolution.ilike("4KLIGHT"))
            else:
                rel_stmt = rel_stmt.where(DownloadLink.resolution == resolution)

        if recent and threshold:
            rel_stmt = rel_stmt.where(DownloadLink.last_checked >= threshold)

        rel_stmt = rel_stmt.order_by(DownloadLink.last_checked.desc())
        
        rel_result = await db.execute(rel_stmt)
        releases = rel_result.scalars().all()
        
        # Secondary grouping by Release Card (Episode, Pack, or unique Movie release)
        release_cards = {}
        for r in releases:
            # Create a "release signature" by removing part indicators and normalizing delimiters
            sig = r.filename or ""
            sig = re.sub(r'[._ ]part\s*\d+', '', sig, flags=re.I)
            sig = re.sub(r'[._ ]pt\s*\d+', '', sig, flags=re.I)
            sig = re.sub(r'\.(rar|zip|7z|html)$', '', sig, flags=re.I)
            # Unify delimiters for better mirror resistance
            sig = re.sub(r'[._\s-]+', '.', sig).lower()
            
            # Broad Group key (The Card): (Season, Episode, Resolution, Language, Source, Quality, Codec)
            card_key = (r.season, r.episode, r.resolution, r.language, r.source_name, r.quality, r.codec, r.network, r.v_quality)
            
            # Sub-release key (The release identity): Based on filename signature
            sub_key = sig
            
            if card_key not in release_cards:
                is_new = False
                if r.last_checked and threshold:
                    l_checked = r.last_checked
                    if l_checked.tzinfo is None:
                        l_checked = l_checked.replace(tzinfo=timezone.utc)
                    is_new = l_checked >= threshold
 
                release_cards[card_key] = {
                    "id": r.id,
                    "season": r.season,
                    "episode": r.episode,
                    "resolution": r.resolution,
                    "language": r.language,
                    "source": r.source_name,
                    "quality": r.quality,
                    "codec": r.codec,
                    "network": r.network,
                    "v_quality": r.v_quality,
                    "source_url": r.source_url,
                    "is_new": is_new,
                    "last_checked": r.last_checked,
                    "sub_releases": {}
                }
            
            card = release_cards[card_key]
            
            if sub_key not in card["sub_releases"]:
                is_sub_new = False
                if r.last_checked and threshold:
                    l_checked = r.last_checked
                    if l_checked.tzinfo is None:
                        l_checked = l_checked.replace(tzinfo=timezone.utc)
                    is_sub_new = l_checked >= threshold

                if is_sub_new:
                    card["is_new"] = True

                card["sub_releases"][sub_key] = {
                    "filename": r.filename,
                    "is_new": is_sub_new,
                    "part_sizes": {},
                    "parts": []
                }
            
            sub = card["sub_releases"][sub_key]
            
            if not any(p["url"] == r.url for p in sub["parts"]):
                # Detect part number
                part_match = re.search(r'Part\s*(\d+)', r.filename or '', re.I)
                part_num = int(part_match.group(1)) if part_match else 1
                
                # Update total bytes only for unique part numbers
                b = r.size_bytes or 0
                if part_num not in sub["part_sizes"] or b > sub["part_sizes"][part_num]:
                    sub["part_sizes"][part_num] = b
                
                sub["parts"].append({
                    "id": r.id,
                    "part": part_num,
                    "size": r.size,
                    "size_bytes": r.size_bytes,
                    "hoster": r.hoster,
                    "url": r.url
                })
            
        # Final formatting for the title group
        release_items = []
        for card in release_cards.values():
            # Convert sub_releases dict to sorted list
            formatted_subs = []
            for sub_key, sub in card["sub_releases"].items():
                total_bytes = sum(sub["part_sizes"].values())
                sub["parts"].sort(key=lambda x: x["part"])
                formatted_subs.append({
                    "filename": sub["filename"],
                    "is_new": sub["is_new"],
                    "total_bytes": total_bytes,
                    "total_size": format_size(total_bytes),
                    "parts": sub["parts"]
                })
            
            card["sub_releases"] = formatted_subs
            release_items.append(card)

        # Group cards by resolution
        resolutions_map = {}
        for card in release_cards.values():
            res = card["resolution"] or "HD"
            if res not in resolutions_map:
                resolutions_map[res] = []
            resolutions_map[res].append(card)
        
        # Sort each resolution list by season/episode (ensure we handle potential string/int mix)
        for res in resolutions_map:
            resolutions_map[res].sort(key=lambda x: (
                int(x["season"]) if x["season"] is not None and str(x["season"]).isdigit() else 0,
                int(x["episode"]) if x["episode"] is not None and str(x["episode"]).isdigit() else 0
            ))

        group_latest = releases[0].last_checked if releases else None
        
        items.append({
            "title": g_title,
            "official_title": g_official,
            "year": g_off_year or g_year,
            "category": g_cat,
            "poster_path": g_poster,
            "plot_en": g_plot_en,
            "plot_fr": g_plot_fr,
            "title_fr": g_title_fr,
            "rating": g_rating,
            "imdb_id": g_imdb,
            "last_updated": group_latest.isoformat() if hasattr(group_latest, "isoformat") else group_latest,
            "resolutions": resolutions_map,
            "count": len(release_cards)
        })
        
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": math.ceil(total / limit) if limit > 0 else 0
    }



@router.post("/scan/force")
async def force_scan(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_scrapers)
    return {"message": "Full discovery scan manually triggered."}

@router.post("/scan/direct")
async def direct_scan(request: ScanRequest, background_tasks: BackgroundTasks):
    """
    Triggers a direct scan of one or more URLs in the background.
    """
    scanner = DirectScanner()
    background_tasks.add_task(scanner.scan_urls, request.urls)
    return {"message": f"Scanning {len(request.urls)} URLs in background..."}

@router.post("/scan/categories")
async def scan_categories(background_tasks: BackgroundTasks):
    from app.core.scheduler import run_categorization
    background_tasks.add_task(run_categorization)
    return {"message": "Categorization of unassigned links triggered."}

@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """
    Returns global statistics using optimized SQL aggregation.
    """
    # Unique Movies (Unique titles)
    movie_unique_stmt = select(func.count(func.distinct(DownloadLink.title))).where(DownloadLink.category == "movie")
    movie_unique_res = await db.execute(movie_unique_stmt)
    unique_movies = movie_unique_res.scalar() or 0
    
    # Total Movie Links
    movie_links_stmt = select(func.count(DownloadLink.id)).where(DownloadLink.category == "movie")
    movie_links_res = await db.execute(movie_links_stmt)
    links_movies = movie_links_res.scalar() or 0
    
    # Unique Series (Unique titles)
    series_unique_stmt = select(func.count(func.distinct(DownloadLink.title))).where(DownloadLink.category == "series")
    series_unique_res = await db.execute(series_unique_stmt)
    unique_series = series_unique_res.scalar() or 0
    
    # Total Series Links
    series_links_stmt = select(func.count(DownloadLink.id)).where(DownloadLink.category == "series")
    series_links_res = await db.execute(series_links_stmt)
    links_series = series_links_res.scalar() or 0
    
    # Total links
    total_links_stmt = select(func.count(DownloadLink.id))
    total_links_res = await db.execute(total_links_stmt)
    total_links = total_links_res.scalar() or 0
    
    # Stats by source
    stmt = select(DownloadLink.source_name, DownloadLink.size)
    result = await db.execute(stmt)
    rows = result.all()
    
    size_by_source = {}
    total_size_bytes = 0
    
    for source, size_str in rows:
        source_name = source or "Unknown"
        bytes_val = parse_size(size_str)
        size_by_source[source_name] = size_by_source.get(source_name, 0) + bytes_val
        total_size_bytes += bytes_val
        
    # Format sizes back to string
    fmt_size_by_source = {src: format_size(val) for src, val in size_by_source.items()}
    
    # Dead links
    dead_links_stmt = select(func.count(DownloadLink.id)).where(DownloadLink.status == "dead")
    dead_links_res = await db.execute(dead_links_stmt)
    dead_links = dead_links_res.scalar() or 0
    
    stats = {
        "unique_movies": unique_movies,
        "unique_series": unique_series,
        "links_movies": links_movies,
        "links_series": links_series,
        "total_movies": links_movies,  # Backwards compatibility
        "total_series": links_series,  # Backwards compatibility
        "total_links": total_links,
        "dead_links": dead_links,
        "total_size": format_size(total_size_bytes),
        "total_size_bytes": total_size_bytes,
        "size_by_source": fmt_size_by_source,
        "size_by_source_raw": size_by_source
    }
    return stats

@router.get("/sources/dashboard")
async def get_sources_dashboard(db: AsyncSession = Depends(get_db)):
    """
    Returns a detailed dashboard of all sources, their health and last additions.
    """
    # 1. Get all configured sources from settings
    configured_sources = {s["name"]: s.get("entry_url") for s in settings.SCRAPER_SOURCES}
    
    # 2. Get stats per source from DownloadLink
    source_stats_stmt = select(
        DownloadLink.source_name,
        func.count(DownloadLink.id).label("count"),
        func.max(DownloadLink.last_checked).label("last_checked")
    ).group_by(DownloadLink.source_name)
    
    res_stats = await db.execute(source_stats_stmt)
    db_stats = {r.source_name: {"count": r.count, "last_checked": r.last_checked} for r in res_stats.all()}
    
    # 3. Get last entry per source
    sources_dashboard = []
    all_names = sorted(list(set(configured_sources.keys()) | set(db_stats.keys())))
    
    for name in all_names:
        if name == "Unknown" or not name: continue
        
        # Get entry_url: preferred from config, fallback from ScrapedURL history
        entry_url = configured_sources.get(name)
        if not entry_url:
            last_scraped_stmt = select(ScrapedURL.url).where(ScrapedURL.source_name == name).order_by(ScrapedURL.last_scraped.desc()).limit(1)
            entry_url = (await db.execute(last_scraped_stmt)).scalar()

        # Find last added link metadata
        last_link_stmt = select(DownloadLink).where(DownloadLink.source_name == name).order_by(DownloadLink.last_checked.desc()).limit(1)
        last_link = (await db.execute(last_link_stmt)).scalar()
        
        # Find last scan status
        last_scan_stmt = select(ScrapedURL).where(ScrapedURL.source_name == name).order_by(ScrapedURL.last_scraped.desc()).limit(1)
        last_scan = (await db.execute(last_scan_stmt)).scalar()
        
        sources_dashboard.append({
            "name": name,
            "entry_url": entry_url,
            "total_items": db_stats.get(name, {}).get("count", 0),
            "last_scan": last_scan.last_scraped.isoformat() if last_scan else None,
            "last_status": last_scan.status if last_scan else "unknown",
            "last_item": {
                "title": last_link.title if last_link else None,
                "url": last_link.source_url if last_link else None,
                "date": last_link.last_checked.isoformat() if last_link else None
            } if last_link else None
        })
        
    return {"sources": sources_dashboard}

@router.get("/sources")
async def get_sources(db: AsyncSession = Depends(get_db)):
    """
    Returns a list of unique source names from the database.
    """
    stmt = select(func.distinct(DownloadLink.source_name)).where(DownloadLink.source_name != None)
    result = await db.execute(stmt)
    sources = result.scalars().all()
    # Sort alphabetically, filtering out empty strings/None
    return sorted([s for s in sources if s])

@router.get("/years")
async def get_years(db: AsyncSession = Depends(get_db)):
    """
    Returns a list of unique years from both DownloadLink and MediaMetadata.
    """
    stmt_dl = select(func.distinct(DownloadLink.year)).where(DownloadLink.year != None)
    stmt_meta = select(func.distinct(MediaMetadata.year)).where(MediaMetadata.year != None)
    
    res_dl = await db.execute(stmt_dl)
    res_meta = await db.execute(stmt_meta)
    
    years = set(res_dl.scalars().all()) | set(res_meta.scalars().all())
    
    # Sort descending, filter None and limit to reasonable amount if needed, 
    # but here we return all unique years.
    return sorted([y for y in years if y], reverse=True)

@router.get("/networks")
async def get_networks(db: AsyncSession = Depends(get_db)):
    """
    Returns a list of unique network names from the database.
    """
    stmt = select(func.distinct(DownloadLink.network)).where(DownloadLink.network != None)
    result = await db.execute(stmt)
    networks = result.scalars().all()
    # Sort alphabetically, filtering out empty strings/None
    return sorted([n for n in networks if n])

@router.get("/tmdb/search")
async def search_tmdb(query: str, type: str = "movie", lang: str = None):
    """
    Search TMDb for a title.
    """
    try:
        from app.services.tmdb import tmdb_service
        search_lang = lang or settings.DEFAULT_LANGUAGE
        if len(search_lang) == 2:
            search_lang = f"{search_lang}-{search_lang.upper()}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            search_params = {
                "api_key": tmdb_service.api_key,
                "query": query,
                "language": search_lang
            }
            
            endpoint = "search/movie" if type == "movie" else "search/tv"
            r = await client.get(f"{tmdb_service.base_url}/{endpoint}", params=search_params)
            r.raise_for_status()
            data = r.json()
            
            # Map to a consistent format for the UI
            results = []
            for res in data.get("results", []):
                date_str = res.get("release_date") or res.get("first_air_date") or ""
                results.append({
                    "id": res.get("id"),
                    "title": res.get("title") or res.get("name"),
                    "year": date_str[:4] if date_str else "N/A",
                    "poster_path": f"https://image.tmdb.org/t/p/w200{res.get('poster_path')}" if res.get("poster_path") else None,
                    "overview": res.get("overview")
                })
            return results
    except Exception as e:
        print(f"[API] TMDb search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class IdentificationRequest(BaseModel):
    imdb_id: Optional[str] = None
    tmdb_id: Optional[int] = None
    title: Optional[str] = None
    year: Optional[int] = None
    category: str = "movie"
    lang: Optional[str] = None
    link_ids: List[int]

@router.post("/releases/identify")
async def identify_release(req: IdentificationRequest, db: AsyncSession = Depends(get_db)):
    """
    Manually identify a release by providing an IMDb ID or searching TMDb.
    """
    try:
        from app.core.categorization import Categorizer
        from app.services.tmdb import tmdb_service
        from app.db.models import MediaMetadata, DownloadLink
        
        # 1. Fetch metadata from TMDb
        res_data = None
        
        if req.imdb_id:
            res_data = await tmdb_service.fetch_metadata_by_imdb_id(req.imdb_id, media_type=req.category)
        elif req.tmdb_id:
            res_data = await tmdb_service.fetch_metadata_by_tmdb_id(req.tmdb_id, media_type=req.category)
        elif req.title:
            res_data = await tmdb_service.fetch_metadata(req.title, req.year, req.category, language=req.lang)
            
        if not res_data:
            raise HTTPException(status_code=404, detail="Could not find metadata for provided info")
            
        # 2. Update MediaMetadata or create if new
        imdb_id = res_data.get("imdb_id") or f"local_{res_data.get('official_title').replace(' ', '_').lower()}"
        
        stmt = select(MediaMetadata).where(MediaMetadata.imdb_id == imdb_id)
        existing_meta = (await db.execute(stmt)).scalar()
        
        if not existing_meta:
            existing_meta = MediaMetadata(
                imdb_id=imdb_id,
                official_title=res_data.get("official_title"),
                title_fr=res_data.get("title_fr"),
                year=res_data.get("year"),
                poster_path=None, 
                plot_en=res_data.get("plot_en"),
                plot_fr=res_data.get("plot_fr"),
                rating=res_data.get("rating")
            )
            db.add(existing_meta)
            await db.flush()
            
        # Download poster if needed (service handles skipping if file exists and valid)
        p_url = res_data.get("poster_url")
        if p_url:
             existing_meta.poster_path = await tmdb_service.download_poster(existing_meta.imdb_id, p_url)

        # 3. Update all provided links
        stmt_links = select(DownloadLink).where(DownloadLink.id.in_(req.link_ids))
        links_res = await db.execute(stmt_links)
        links = links_res.scalars().all()
        
        for link in links:
            link.imdb_id = existing_meta.imdb_id
            link.title = existing_meta.official_title
            link.year = existing_meta.year
            link.category = req.category
            
        await db.commit()
        return {"status": "success", "imdb_id": existing_meta.imdb_id}
        
    except Exception as e:
        print(f"[API] Manual identification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
