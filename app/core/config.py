import os
import yaml
from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import BaseModel

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
    
    # AllDebrid API Settings (Environment variable takes priority)
    _yaml_alldebrid = _yaml_config.get("alldebrid", {})
    ALLDEBRID_API_KEY: str = os.getenv("ALLDEBRID_API_KEY", _yaml_alldebrid.get("api_key", ""))
    ALLDEBRID_AGENT: str = _yaml_alldebrid.get("agent", "ddl-tower")
    
    # Scraper Settings
    SCAN_INTERVAL_MINUTES: int = _yaml_config.get("scan_interval_minutes", 15)
    SCAN_NOVELTY_MULTIPLIER: int = _yaml_config.get("scan_novelty_multiplier", 2)
    DIRECT_SCAN_PATTERNS: List[str] = _yaml_config.get("direct_scan_patterns", [])
    
    @property
    def SCRAPER_SOURCES(self) -> List[dict]:
        # Directly read the 'sources' block from the main YAML
        return _yaml_config.get("sources", [])

    class Config:
        env_file = ".env"

settings = Settings()
