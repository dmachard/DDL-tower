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

    def organize_file(self, file_path: str, category: str = "movie", title: str = None, year: int = None) -> bool:
        """
        Organizes a file based on its category.
        - Movies: Moves to movies_dir, creates symlink in downloads.
        - Series: Moves to series_dir/(Year - Title)/, creates symlink in downloads.
        """
        if category not in ["movie", "series"]:
            return False

        try:
            src = Path(file_path)
            if not src.exists():
                print(f"[LIBRARY] Error: Source file {file_path} does not exist.")
                return False

            # Determine destination folder
            if category == "movie":
                target_base_dir = self.movies_dir
            else: # series
                s_title = self._sanitize_path(title or "Unknown Series")
                folder_name = f"{year} - {s_title}" if year else s_title
                target_base_dir = self.series_dir / folder_name
            
            # Ensure destination directory exists
            target_base_dir.mkdir(parents=True, exist_ok=True)
            
            dest = target_base_dir / src.name
            
            # If the destination already exists, we don't overwrite
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

library_service = LibraryService()
