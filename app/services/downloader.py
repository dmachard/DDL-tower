import aiohttp
import os
import re
from typing import List, Optional
from pathlib import Path
from app.core.config import settings
from app.services.extraction import extraction_service

class DownloaderService:
    def __init__(self, download_dir: str = settings.DOWNLOAD_DIR):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        # Keys are group names (usually filename without .partX.rar)
        # Value: {"files": {filename: info}, "status": ..., "progress": ...}
        self.active_downloads = {}

    def _get_group_name(self, filename: str) -> str:
        """Returns the base name for grouping parts."""
        # Remove .part01.rar, .part1.rar patterns
        name = re.sub(r'\.part\d+\.rar$', '', filename, flags=re.I)
        # Also remove .rar if not multi-part
        name = re.sub(r'\.rar$', '', name, flags=re.I)
        return name

    def pre_register_files(self, files: List[tuple]):
        """
        Pre-registers a list of (url, filename) before the downloads start.
        Ensures the UI shows the full group structure immediately.
        """
        for _, filename in files:
            if not filename: continue
            group_name = self._get_group_name(filename)
            if group_name not in self.active_downloads:
                self.active_downloads[group_name] = {
                    "name": group_name,
                    "files": {},
                    "progress": 0,
                    "total": 0,
                    "downloaded": 0,
                    "status": "waiting",
                    "extraction_triggered": False
                }
            group = self.active_downloads[group_name]
            if filename not in group["files"]:
                group["files"][filename] = {
                    "progress": 0,
                    "total": 0,
                    "downloaded": 0,
                    "status": "waiting"
                }

    async def download_file(self, url: str, filename: str = None, category: str = None) -> str:
        """
        Downloads a file from a URL to the download directory.
        Returns the path to the downloaded file.
        """
        async with aiohttp.ClientSession() as session:
            try:
                print(f"[DOWNLOADER] Starting download of {url}...")
                async with session.get(url) as response:
                    if response.status != 200:
                        print(f"[DOWNLOADER] Failed to download {url}: HTTP {response.status}")
                        return None
                    
                    if not filename:
                        # Try to get filename from Content-Disposition
                        cd = response.headers.get("Content-Disposition")
                        if cd and "filename=" in cd:
                            filename = cd.split("filename=")[1].strip('"')
                        else:
                            filename = os.path.basename(url.split('?')[0])
                   
                    group_name = self._get_group_name(filename)
                    file_path = self.download_dir / filename
                    total_size = int(response.headers.get('Content-Length', 0))
 
                    if group_name not in self.active_downloads:

                        self.active_downloads[group_name] = {
                            "name": group_name,
                            "files": {},
                            "progress": 0,
                            "total": 0,
                            "downloaded": 0,
                            "status": "downloading",
                            "extraction_triggered": False
                        }
                    
                    group = self.active_downloads[group_name]
                    # Update status if it was previously set to something else (like waiting)
                    if group["status"] not in ["extracting", "error"]:
                        group["status"] = "downloading"

                    # Update or create file entry
                    file_info = group["files"].get(filename, {})
                    group["files"][filename] = {
                        "progress": file_info.get("progress", 0),
                        "total": total_size,
                        "downloaded": file_info.get("downloaded", 0),
                        "status": "downloading"
                    }
                    
                    # Recalculate group total (only add if we hadn't already set total for this file)
                    if file_info.get("total") == 0:
                        group["total"] += total_size

                    downloaded_part = 0
                    with open(file_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(1024 * 64):
                            f.write(chunk)
                            chunk_len = len(chunk)
                            downloaded_part += chunk_len
                            
                            # Update group stats
                            group["downloaded"] += chunk_len
                            group["files"][filename]["downloaded"] = downloaded_part
                            if total_size > 0:
                                group["files"][filename]["progress"] = round((downloaded_part / total_size) * 100, 1)
                            
                            if group["total"] > 0:
                                group["progress"] = round((group["downloaded"] / group["total"]) * 100, 1)
                    
                    print(f"[DOWNLOADER] Finished download of {filename}")
                    
                    group["files"][filename]["progress"] = 100
                    group["files"][filename]["status"] = "done"
                    
                    # Check for extraction if enabled
                    # Atomic check and set for extraction_triggered
                    if settings.EXTRACT_RAR and not group.get("extraction_triggered"):
                        if extraction_service.should_extract(str(file_path), self.active_downloads):
                            group["extraction_triggered"] = True
                            group["status"] = "extracting"
                            group["progress"] = 100
                            
                            # Call extraction with category
                            success = extraction_service.extract_rar(str(file_path), self.active_downloads, category=category)
                            if not success:
                                group["status"] = "error"
                                group["error"] = "Extraction failed (Check logs/archives)"
                                return str(file_path)
                            else:
                                print(f"[DOWNLOADER] Extraction successful for {group_name}, clearing group.")
                                group["status"] = "done"
                                self.active_downloads.pop(group_name, None)
                                return str(file_path)
                    
                    # If we reach here, either it's not a RAR or extraction wasn't triggered
                    if group["status"] != "error":
                        # If it's a movie and it wasn't a RAR, organize it now
                        if category == "movie" and not self.is_rar(str(file_path)):
                             from app.services.library_service import library_service
                             library_service.organize_file(str(file_path), category)

                        group["files"].pop(filename, None)
                        if not group["files"]:
                             self.active_downloads.pop(group_name, None)
                        
                    return str(file_path)
            except Exception as e:
                print(f"[DOWNLOADER] Exception during download of {url}: {str(e)}")
                if group_name in self.active_downloads:
                     self.active_downloads[group_name]["status"] = "error"
                     self.active_downloads[group_name]["error"] = str(e)
                return None



downloader_service = DownloaderService()

