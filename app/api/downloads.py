import asyncio
import shutil
from typing import List
from pathlib import Path
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.utils import format_size
from app.services.downloader import downloader_service
from app.services.alldebrid import AllDebridClient
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
    
    if not path.exists():
         raise HTTPException(status_code=404, detail="File not found")
    
    if path.is_dir():
         raise HTTPException(status_code=400, detail="Cannot download a directory. Please extract it first.")
    
    try:
        path.resolve().relative_to(Path(settings.DOWNLOAD_DIR).resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    return FileResponse(path, filename=filename)

async def run_download_task(urls: List[str]):
    """
    Background task to unlock and download files.
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

    # 2. Register all files
    downloader_service.pre_register_files(valid_downloads)

    # 3. Start downloads concurrently
    sem = asyncio.Semaphore(5)

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
