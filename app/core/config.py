import os
import yaml
from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import BaseModel, ConfigDict

# Configuration directory path
CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

# Initial loading
_yaml_config = {}
if CONFIG_FILE.exists():
    try:
        with open(CONFIG_FILE, "r") as f:
            _yaml_config = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"Error loading config.yaml: {e}")

class Settings(BaseSettings):
    # App General Settings
    APP_NAME: str = _yaml_config.get("app_name", "DDL Tower")
    DEBUG: bool = _yaml_config.get("debug", True)
    DEFAULT_LANGUAGE: str = _yaml_config.get("default_language", "fr")
    
    # Database Settings
    DATABASE_URL: str = _yaml_config.get("database_url", "sqlite+aiosqlite:///./data/ddl.db")
    
    # Downloader API Settings (Environment variable takes priority)
    _yaml_downloader = _yaml_config.get("downloader", {})
    _yaml_alldebrid = _yaml_downloader.get("alldebrid", _yaml_config.get("alldebrid", {}))
    _yaml_realdebrid = _yaml_downloader.get("realdebrid", {})
    _yaml_bestdebrid = _yaml_downloader.get("bestdebrid", {})

    ALLDEBRID_API_KEY: str = os.getenv("ALLDEBRID_API_KEY", _yaml_alldebrid.get("api_key", ""))
    ALLDEBRID_AGENT: str = _yaml_alldebrid.get("agent", "ddl-tower")
    
    REALDEBRID_API_KEY: str = os.getenv("REALDEBRID_API_KEY", _yaml_realdebrid.get("api_key", ""))
    BESTDEBRID_API_KEY: str = os.getenv("BESTDEBRID_API_KEY", _yaml_bestdebrid.get("api_key", ""))
    
    # Download Settings
    DOWNLOAD_DIR: str = os.getenv("DOWNLOAD_DIR", _yaml_config.get("download_dir", "/app/data/download"))
    LIBRARY_MOVIES_DIR: str = os.getenv("LIBRARY_MOVIES_DIR", _yaml_config.get("library_movies_dir", "/app/data/films"))
    LIBRARY_SERIES_DIR: str = os.getenv("LIBRARY_SERIES_DIR", _yaml_config.get("library_series_dir", "/app/data/series"))
    POSTER_DIR: str = os.getenv("POSTER_DIR", _yaml_config.get("poster_dir", "/app/data/posters"))
    EXTRACT_RAR: bool = _yaml_config.get("extract_rar", True)
    DELETE_RAR_AFTER_EXTRACTION: bool = _yaml_config.get("delete_rar_after_extraction", True)
    KEEP_ONLY_VIDEO_FILES: bool = _yaml_config.get("keep_only_video_files", True)
    VIDEO_EXTENSIONS: List[str] = [".mkv", ".mp4", ".avi", ".m4v", ".mov", ".wmv", ".ts"]
    
    # Scraper Settings
    SCAN_INTERVAL_MINUTES: int = _yaml_config.get("scan_interval_minutes", 15)
    SCAN_NOVELTY_MULTIPLIER: int = _yaml_config.get("scan_novelty_multiplier", 2)
    BROWSER_URL: Optional[str] = _yaml_config.get("browser_url", None)
    WEBTOP_CONTAINER_NAME: str = _yaml_config.get("webtop_container_name", "ddltower-browser")
    DIRECT_SCAN_PATTERNS: List[str] = _yaml_config.get("direct_scan_patterns", [])
    _yaml_tmdb = _yaml_config.get("tmdb", {})
    TMDB_API_KEY: str = os.getenv("TMDB_API_KEY", _yaml_tmdb.get("api_key", ""))
    
    # Translation Settings (MyMemory)
    _yaml_mymemory = _yaml_config.get("mymemory", {})
    MYMEMORY_EMAIL: str = _yaml_mymemory.get("email", "dmachard@gmail.com")
    
    @property
    def SCRAPER_SOURCES(self) -> List[dict]:
        # Directly read the 'sources' block from the main YAML
        return _yaml_config.get("sources") or []

    model_config = ConfigDict(env_file=".env", extra="ignore")

settings = Settings()
