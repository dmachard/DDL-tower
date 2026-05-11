import aiohttp
import asyncio
import os
import re
from typing import List, Optional
from pathlib import Path
from app.core.config import settings
from app.services.extraction import extraction_service

class DownloaderService:
    def __init__(self, download_dir: str = settings.DOWNLOAD_DIR):
        self.download_dir = Path(download_dir)
        try:
            self.download_dir.mkdir(parents=True, exist_ok=True)
        except:
            # Fallback for CI/Read-only environments
            pass
        # Keys are group names (usually filename without .partX.rar)
        # Value: {"files": {filename: info}, "status": ..., "progress": ...}
        self.active_downloads = {}
        self.lock = asyncio.Lock()

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

    async def download_file(self, url: str, filename: str = None, category: str = None, title: str = None, year: int = None, is_auto: bool = False, imdb_id: str = None, season: str = None, episode: str = None, resolution: str = None, quality: str = None, language: str = None, v_quality: str = None, codec: str = None, network: str = None, audio: str = None, channels: str = None) -> str:
        """
        Downloads a file from a URL to the download directory with resume support and retries.
        Uses a global lock to ensure sequential downloads (one by one).
        """
        async with self.lock:
            return await self._do_download(url, filename, category, title, year, is_auto, imdb_id, season, episode, resolution, quality, language, v_quality, codec, network, audio, channels)

    async def _do_download(self, url: str, filename: str = None, category: str = None, title: str = None, year: int = None, is_auto: bool = False, imdb_id: str = None, season: str = None, episode: str = None, resolution: str = None, quality: str = None, language: str = None, v_quality: str = None, codec: str = None, network: str = None, audio: str = None, channels: str = None) -> str:
        max_retries = 5
        retry_delay = 2
        
        # Initial filename resolution
        if not filename:
             async with aiohttp.ClientSession() as session:
                 async with session.head(url, allow_redirects=True) as resp:
                     cd = resp.headers.get("Content-Disposition")
                     if cd and "filename=" in cd:
                         filename = cd.split("filename=")[1].strip('"')
                     else:
                         filename = os.path.basename(url.split('?')[0])
        
        if not filename:
            filename = "unknown_file"

        file_path = self.download_dir / filename
        group_name = self._get_group_name(filename)
        
        # Ensure group entry exists
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
        if group["status"] not in ["extracting", "error"]:
            group["status"] = "downloading"

        for attempt in range(max_retries):
            try:
                downloaded_on_disk = file_path.stat().st_size if file_path.exists() else 0
                headers = {}
                if downloaded_on_disk > 0:
                    headers["Range"] = f"bytes={downloaded_on_disk}-"
                    print(f"[DOWNLOADER] Attempting to resume {filename} from {downloaded_on_disk} bytes (Attempt {attempt+1})")
                else:
                    print(f"[DOWNLOADER] Starting download of {filename} (Attempt {attempt+1})")

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers) as response:
                        if response.status not in [200, 206]:
                            print(f"[DOWNLOADER] Failed to download {url}: HTTP {response.status}")
                            if attempt == max_retries - 1: return None
                            await asyncio.sleep(retry_delay * (attempt + 1))
                            continue

                        # Handle partial content or full content
                        is_resume = (response.status == 206)
                        if not is_resume:
                             downloaded_on_disk = 0 # Server doesn't support range or we didn't ask
                        
                        content_length = int(response.headers.get('Content-Length', 0))
                        total_size = content_length + downloaded_on_disk if is_resume else content_length
                        
                        # Initialize or update file info
                        file_info = group["files"].get(filename, {})
                        old_total = file_info.get("total", 0)
                        
                        group["files"][filename] = {
                            "progress": file_info.get("progress", 0),
                            "total": total_size,
                            "downloaded": downloaded_on_disk,
                            "status": "downloading"
                        }
                        
                        # Adjust group total if this is the first time we know the size
                        if old_total == 0:
                            group["total"] += total_size
                        
                        mode = "ab" if is_resume else "wb"
                        with open(file_path, mode) as f:
                            async for chunk in response.content.iter_chunked(1024 * 64):
                                f.write(chunk)
                                chunk_len = len(chunk)
                                
                                # Update stats
                                group["downloaded"] += chunk_len
                                group["files"][filename]["downloaded"] += chunk_len
                                
                                if total_size > 0:
                                    prog = round((group["files"][filename]["downloaded"] / total_size) * 100, 1)
                                    group["files"][filename]["progress"] = prog
                                
                                if group["total"] > 0:
                                    group["progress"] = round((group["downloaded"] / group["total"]) * 100, 1)

                        # Success!
                        print(f"[DOWNLOADER] Finished download of {filename}")
                        group["files"][filename]["progress"] = 100
                        group["files"][filename]["status"] = "done"
                        
                        # Trigger extraction or organization
                        return await self._finalize_download(file_path, filename, group_name, category, title, year, is_auto, imdb_id, season, episode, resolution, quality, language, v_quality, codec, network, audio, channels)

            except (aiohttp.ClientPayloadError, aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
                print(f"[DOWNLOADER] Connection error during {filename} (attempt {attempt+1}): {str(e)}")
                if attempt == max_retries - 1:
                    group["status"] = "error"
                    group["error"] = f"Download failed after {max_retries} attempts: {str(e)}"
                    return None
                await asyncio.sleep(retry_delay * (attempt + 1))
            except Exception as e:
                print(f"[DOWNLOADER] Unexpected exception during download of {url}: {str(e)}")
                group["status"] = "error"
                group["error"] = str(e)
                return None
        
        return None

    async def _finalize_download(self, file_path: Path, filename: str, group_name: str, category: str, title: str, year: int, is_auto: bool = False, imdb_id: str = None, season: str = None, episode: str = None, resolution: str = None, quality: str = None, language: str = None, v_quality: str = None, codec: str = None, network: str = None, audio: str = None, channels: str = None) -> str:
        group = self.active_downloads.get(group_name)
        if not group: return str(file_path)

        if settings.EXTRACT_RAR and not group.get("extraction_triggered"):
            if extraction_service.should_extract(str(file_path), self.active_downloads):
                group["extraction_triggered"] = True
                group["status"] = "extracting"
                group["progress"] = 100
                
                success = extraction_service.extract_rar(str(file_path), self.active_downloads, category=category, title=title, year=year, season=season, episode=episode)
                if not success:
                    group["status"] = "error"
                    group["error"] = "Extraction failed"
                    return str(file_path)
                else:
                    group["status"] = "done"
                    self.active_downloads.pop(group_name, None)
                    return str(file_path)
        
        # If not RAR or extraction not triggered
        if group["status"] != "error":
            if category in ["movie", "series"] and not extraction_service.is_rar(str(file_path)):
                 from app.services.library_service import library_service
                 library_service.organize_file(str(file_path), category, title=title, year=year, season=season, episode=episode)

            # Record in history
            try:
                from app.db.database import AsyncSessionLocal
                from app.db.models import DownloadHistory
                async with AsyncSessionLocal() as session:
                    history = DownloadHistory(
                        title=title or filename,
                        filename=filename,
                        category=category,
                        year=year,
                        season=season,
                        episode=episode,
                        resolution=resolution,
                        quality=quality,
                        language=language,
                        v_quality=v_quality,
                        codec=codec,
                        network=network,
                        audio=audio,
                        channels=channels,
                        is_auto=is_auto,
                        imdb_id=imdb_id
                    )
                    session.add(history)
                    await session.commit()
            except Exception as he:
                print(f"[DOWNLOADER] Error saving history: {he}")

            group["files"].pop(filename, None)
            if not group["files"]:
                 self.active_downloads.pop(group_name, None)
            
        return str(file_path)



downloader_service = DownloaderService()

