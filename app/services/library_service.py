import os
import shutil
import re
from pathlib import Path
from app.core.config import settings

class LibraryService:
    def __init__(self):
        self.movies_dir = Path(settings.LIBRARY_MOVIES_DIR)
        self.series_dir = Path(settings.LIBRARY_SERIES_DIR)
        self.movies_dir.mkdir(parents=True, exist_ok=True)
        self.series_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_path(self, name: str) -> str:
        """Removes or replaces characters that are invalid for file paths."""
        if not name: return "Unknown"
        # Replace : / \ with space or dash
        s = re.sub(r'[:/\\]', ' ', name)
        # Remove other potentially problematic characters
        s = re.sub(r'[<>|?*"]', '', s)
        return s.strip()

    def organize_file(self, file_path: str, category: str = "movie", title: str = None, year: int = None, season: str = None, episode: str = None) -> bool:
        """
        Organizes a file based on its category and removes older versions if they exist.
        - Movies: Moves to movies_dir, deletes other files with same title/year.
        - Series: Moves to series_dir/(Title (Year))/, deletes other files with same SxxExx.
        """
        if category not in ["movie", "series"]:
            return False

        try:
            src = Path(file_path)
            if not src.exists():
                print(f"[LIBRARY] Error: Source file {file_path} does not exist.")
                return False

            # Determine destination folder and Cleanup old versions
            if category == "movie":
                target_base_dir = self.movies_dir
                if title:
                    s_title = self._sanitize_path(title)
                    clean_title = s_title.replace(' ', '.')
                    for item in target_base_dir.iterdir():
                        if item.is_file() and item.name != src.name:
                            # Basic match: title in filename + year in filename
                            if clean_title.lower() in item.name.lower().replace(' ', '.'):
                                if not year or str(year) in item.name:
                                    print(f"[LIBRARY] Deleting old movie version: {item.name}")
                                    try: item.unlink()
                                    except: pass
            else: # series
                s_title = self._sanitize_path(title or "Unknown-Series")
                # Capitalize each word for cleaner default names (e.g., "FROM" -> "From")
                s_title = s_title.title()
                folder_name = f"{s_title} ({year})" if year else s_title
                
                target_base_dir = self.series_dir / folder_name
                
                # Check for existing folder with different case to avoid duplicates
                if self.series_dir.exists():
                    for existing in self.series_dir.iterdir():
                        if existing.is_dir() and existing.name.lower() == folder_name.lower():
                            target_base_dir = existing
                            break
                            
                target_base_dir.mkdir(parents=True, exist_ok=True)
                
                # Cleanup old episode versions
                if season and episode:
                    s_num = str(season).zfill(2)
                    e_num = str(episode).zfill(2)
                    patterns = [f"S{s_num}E{e_num}", f"S{s_num} E{e_num}"]
                    for item in target_base_dir.iterdir():
                        if item.is_file() and item.name != src.name:
                            if any(p in item.name.upper() for p in patterns):
                                print(f"[LIBRARY] Deleting old episode version: {item.name}")
                                try: item.unlink()
                                except: pass
            
            dest = target_base_dir / src.name
            
            # If the destination already exists (exact same filename), we don't overwrite
            if dest.exists():
                print(f"[LIBRARY] Skipping: {src.name} already exists in library ({dest})")
                return False

            print(f"[LIBRARY] Moving {src.name} to {target_base_dir}...")
            
            # 1. Move the real file to the library
            shutil.move(str(src), str(dest))
            
            # 2. Create a symlink in the original location pointing to the library
            os.symlink(str(dest), str(src))
            
            print(f"[LIBRARY] Successfully organized {category} {src.name} (Linked to {dest})")
            return True

        except Exception as e:
            print(f"[LIBRARY] Error organizing {category} {file_path}: {e}")
            return False

    def find_in_library(self, filename: str) -> Optional[Path]:
        """
        Checks if a file with the same name exists anywhere in the library.
        Returns the Path if found, None otherwise.
        """
        # Check movies (direct child of movies_dir)
        movie_path = self.movies_dir / filename
        if movie_path.exists():
            return movie_path
        
        # Check series (one level deep: series_dir / Series Folder / filename)
        if self.series_dir.exists():
            for folder in self.series_dir.iterdir():
                if folder.is_dir():
                    p = folder / filename
                    if p.exists():
                        return p
        
        return None

library_service = LibraryService()
