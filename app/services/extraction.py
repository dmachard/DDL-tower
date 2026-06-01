import os
import shutil
import subprocess
import re
from pathlib import Path
from typing import List, Optional
from app.core.config import settings

class ExtractionService:
    def __init__(self, download_dir: str = settings.DOWNLOAD_DIR):
        self.download_dir = Path(download_dir)

    def is_rar(self, file_path: str) -> bool:
        """Checks if a file is a RAR archive."""
        return file_path.lower().endswith('.rar')

    def get_rar_parts(self, file_path: str) -> List[str]:
        """
        If it's a multi-part RAR, returns the list of all parts.
        Otherwise returns only the file itself.
        """
        path = Path(file_path)
        name = path.name
        
        # Detection of multi-part patterns: .part01.rar, .part1.rar, .r01, etc.
        part_match = re.search(r'\.part(\d+)\.rar$', name, re.I)
        if part_match:
            base = name[:part_match.start()]
            pattern = re.compile(re.escape(base) + r'\.part\d+\.rar$', re.I)
            return [str(f) for f in path.parent.glob('*') if pattern.match(f.name)]
        
        return [str(path)]

    def check_missing_parts(self, file_path: str) -> List[int]:
        """
        For a multi-part RAR, returns a list of missing part numbers.
        If no parts are missing (or it's not a multi-part RAR), returns an empty list.
        """
        path = Path(file_path)
        name = path.name
        part_match = re.search(r'\.part(\d+)\.rar$', name, re.I)
        if not part_match:
            return []

        base = name[:part_match.start()]
        pattern = re.compile(re.escape(base) + r'\.part(\d+)\.rar$', re.I)
        
        # Scan directory for existing parts and extract their numbers
        existing_part_numbers = set()
        for f in path.parent.glob('*'):
            m = pattern.match(f.name)
            if m:
                existing_part_numbers.add(int(m.group(1)))
                
        if not existing_part_numbers:
            return []
            
        max_part = max(existing_part_numbers)
        # Determine if parts start at 0 or 1
        start_part = 0 if 0 in existing_part_numbers else 1
        
        expected_parts = set(range(start_part, max_part + 1))
        missing = sorted(list(expected_parts - existing_part_numbers))
        return missing

    def should_extract(self, file_path: str, active_downloads: dict = None) -> bool:
        """
        Determines if this file should trigger an extraction.
        If it's a multi-part RAR, it only triggers if all parts are present on disk
        and no other parts are currently downloading for the same group.
        """
        path = Path(file_path)
        name = path.name
        
        if not self.is_rar(file_path):
            return False
            
        part_match = re.search(r'\.part(\d+)\.rar$', name, re.I)
        if part_match:
            # 1. Check if any parts are missing on disk
            missing_parts = self.check_missing_parts(file_path)
            if missing_parts:
                print(f"[EXTRACTION] Skipping {name} because some parts are missing: {missing_parts}")
                return False

            # 2. Check if all files in this group are finished in active_downloads
            if active_downloads:
                base = name[:part_match.start()]
                
                # Find the group in active_downloads
                for group_name, group_info in active_downloads.items():
                    if group_name.lower() in base.lower() or base.lower() in group_name.lower():
                        # Check if all files in this group are finished
                        for fn, info in group_info.get("files", {}).items():
                            if info.get("status") != "done" and info.get("progress", 0) < 100:
                                print(f"[EXTRACTION] Skipping {name} for now because {fn} is not done (status: {info.get('status')}, {info.get('progress', 0)}%).")
                                return False
        
        return True


    def get_first_part(self, file_path: str) -> str:
        """Finds the first volume of a multi-part archive."""
        parts = self.get_rar_parts(file_path)
        if not parts:
            return file_path
        # Sort parts lexicographically. .part1.rar or .rar usually comes first.
        parts.sort()
        return parts[0]

    async def extract_rar(self, file_path: str, active_downloads: dict = None, category: str = None, title: str = None, year: int = None, season: str = None, episode: str = None) -> tuple:
        """
        Extracts a RAR archive using the system unrar command.
        Ensures extraction starts from the first volume.
        Returns a tuple: (success: bool, promoted_files: List[str])
        """
        # We need to import library_service here to avoid circular imports if any
        from app.services.library_service import library_service
        
        if not self.should_extract(file_path, active_downloads):
            return False, []

        path = Path(file_path)
        # Identify the first volume to start extraction
        first_part_path = Path(self.get_first_part(file_path))
        
        # Create a destination folder with the same name as the archive (without extension)
        folder_name = re.sub(r'\.part\d+\.rar$', '', path.name, flags=re.I)
        folder_name = re.sub(r'\.rar$', '', folder_name, flags=re.I)
        
        dest_dir = path.parent / folder_name
        dest_dir.mkdir(parents=True, exist_ok=True)

        print(f"[EXTRACTION] Starting extraction from {first_part_path.name} to {dest_dir}...")
        
        try:
            # -o+ : overwrite existing files
            # -y : assume yes on all queries
            # x : eXtract with full paths
            import asyncio
            proc = await asyncio.create_subprocess_exec(
                "unrar", "x", "-o+", "-y", str(first_part_path), str(dest_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode == 0:
                print(f"[EXTRACTION] Successfully extracted {path.name}")
                
                # 1. Cleanup: Delete RAR parts
                if settings.DELETE_RAR_AFTER_EXTRACTION:
                    parts = self.get_rar_parts(file_path)
                    for part in parts:
                        try:
                            if os.path.exists(part):
                                os.remove(part)
                                print(f"[EXTRACTION] Deleted archive part: {Path(part).name}")
                        except Exception as e:
                            print(f"[EXTRACTION] Could not delete {part}: {e}")
                
                # 2. Cleanup: Delete everything that is NOT a video file
                video_files = []
                print(f"[EXTRACTION] Cleaning up non-video files in {dest_dir}...")
                for root, dirs, files in os.walk(dest_dir, topdown=False):
                    for file in files:
                        file_p = Path(root) / file
                        if file_p.suffix.lower() in settings.VIDEO_EXTENSIONS:
                            video_files.append(file_p)
                        else:
                            try:
                                file_p.unlink()
                                print(f"[EXTRACTION] Deleted non-video: {file}")
                            except Exception as e:
                                print(f"[EXTRACTION] Could not delete {file_p}: {e}")
                    
                    # Remove empty subdirectories
                    for d in dirs:
                        dir_path = Path(root) / d
                        try:
                            if dir_path.exists() and not any(dir_path.iterdir()):
                                dir_path.rmdir()
                        except:
                            pass
                
                # 3. Promote video file to root and remove empty folder
                promoted_files = []
                if video_files:
                    # If multiple video files, we move all of them to parent
                    for video_p in video_files:
                        new_path = path.parent / video_p.name
                        try:
                            if not new_path.exists():
                                shutil.move(str(video_p), str(new_path))
                                print(f"[EXTRACTION] Promoted {video_p.name} to {path.parent}")
                                promoted_files.append(video_p.name)
                                
                                # Library Organization (Movies & Series)
                                if category in ["movie", "series"]:
                                    library_service.organize_file(str(new_path), category, title=title, year=year, season=season, episode=episode)
                            else:
                                print(f"[EXTRACTION] {video_p.name} already exists in destination, skipping move.")
                                promoted_files.append(video_p.name)
                        except Exception as e:
                            print(f"[EXTRACTION] Could not move {video_p.name}: {e}")
                    
                    # Finally remove the folder if empty or if we decided so
                    try:
                        if dest_dir.exists():
                            shutil.rmtree(dest_dir)
                            print(f"[EXTRACTION] Removed temporary folder {dest_dir}")
                    except Exception as e:
                        print(f"[EXTRACTION] Could not remove folder {dest_dir}: {e}")

                return True, promoted_files
            else:
                stderr_dec = stderr.decode('utf-8', errors='replace')
                print(f"[EXTRACTION] Failed to extract {path.name}: {stderr_dec}")
                return False, []
                
        except Exception as e:
            print(f"[EXTRACTION] Exception during extraction of {path.name}: {str(e)}")
            return False, []


extraction_service = ExtractionService()
