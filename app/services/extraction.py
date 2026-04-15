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

    def should_extract(self, file_path: str, active_downloads: dict = None) -> bool:
        """
        Determines if this file should trigger an extraction.
        If it's a multi-part RAR, it only triggers if no other parts 
        are currently downloading for the same group.
        """
        path = Path(file_path)
        name = path.name
        
        if not self.is_rar(file_path):
            return False
            
        part_match = re.search(r'\.part(\d+)\.rar$', name, re.I)
        if part_match and active_downloads:
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

    def extract_rar(self, file_path: str, active_downloads: dict = None) -> bool:
        """
        Extracts a RAR archive using the system unrar command.
        Ensures extraction starts from the first volume.
        """
        if not self.should_extract(file_path, active_downloads):
            return False

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
            result = subprocess.run(
                ["unrar", "x", "-o+", "-y", str(first_part_path), str(dest_dir)],
                capture_output=True,
                text=True,
                errors='replace'
            )
            
            if result.returncode == 0:
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
                
                # 2. Cleanup: Delete everything that is NOT mkv
                video_files = []
                print(f"[EXTRACTION] Cleaning up non-MKV files in {dest_dir}...")
                for root, dirs, files in os.walk(dest_dir, topdown=False):
                    for file in files:
                        file_p = Path(root) / file
                        if file_p.suffix.lower() == '.mkv':
                            video_files.append(file_p)
                        else:
                            try:
                                file_p.unlink()
                                print(f"[EXTRACTION] Deleted non-MKV: {file}")
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
                if video_files:
                    # If multiple MKVs, we move all of them to parent
                    for video_p in video_files:
                        new_path = path.parent / video_p.name
                        try:
                            if not new_path.exists():
                                shutil.move(str(video_p), str(new_path))
                                print(f"[EXTRACTION] Promoted {video_p.name} to {path.parent}")
                            else:
                                print(f"[EXTRACTION] {video_p.name} already exists in destination, skipping move.")
                        except Exception as e:
                            print(f"[EXTRACTION] Could not move {video_p.name}: {e}")
                    
                    # Finally remove the folder if empty or if we decided so
                    try:
                        if dest_dir.exists():
                            shutil.rmtree(dest_dir)
                            print(f"[EXTRACTION] Removed temporary folder {dest_dir}")
                    except Exception as e:
                        print(f"[EXTRACTION] Could not remove folder {dest_dir}: {e}")

                return True
            else:
                print(f"[EXTRACTION] Failed to extract {path.name}: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"[EXTRACTION] Exception during extraction of {path.name}: {str(e)}")
            return False


extraction_service = ExtractionService()
