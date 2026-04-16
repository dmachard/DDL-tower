import os
import shutil
from pathlib import Path
from app.core.config import settings

class LibraryService:
    def __init__(self):
        self.movies_dir = Path(settings.LIBRARY_MOVIES_DIR)
        self.movies_dir.mkdir(parents=True, exist_ok=True)

    def organize_file(self, file_path: str, category: str = "movie") -> bool:
        """
        Organizes a file based on its category.
        For movies: Moves the file to the library and creates a symlink in downloads.
        """
        if category != "movie":
            # For now, we only handle movies as per user request
            return False

        try:
            src = Path(file_path)
            if not src.exists():
                print(f"[LIBRARY] Error: Source file {file_path} does not exist.")
                return False

            # Ensure destination directory exists
            self.movies_dir.mkdir(parents=True, exist_ok=True)
            
            dest = self.movies_dir / src.name
            
            # If the destination already exists, we don't overwrite
            if dest.exists():
                print(f"[LIBRARY] Skipping: {src.name} already exists in library ({dest})")
                return False

            print(f"[LIBRARY] Moving {src.name} to {self.movies_dir}...")
            
            # 1. Move the real file to the library
            shutil.move(str(src), str(dest))
            
            # 2. Create a symlink in the original location pointing to the library
            # Note: We use the absolute path of the destination for the symlink
            os.symlink(str(dest), str(src))
            
            print(f"[LIBRARY] Successfully organized {src.name} (Linked to {dest})")
            return True

        except Exception as e:
            print(f"[LIBRARY] Error organizing movie {file_path}: {e}")
            return False

library_service = LibraryService()
