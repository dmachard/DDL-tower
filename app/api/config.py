from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()

@router.get("/config")
async def get_config():
    """
    Returns app configuration for the frontend.
    """
    return {
        "default_language": settings.DEFAULT_LANGUAGE,
        "app_name": settings.APP_NAME,
        "alldebrid_enabled": bool(settings.ALLDEBRID_API_KEY and settings.ALLDEBRID_API_KEY != "[YOUR_KEY]"),
        "realdebrid_enabled": bool(settings.REALDEBRID_API_KEY and settings.REALDEBRID_API_KEY != "[YOUR_KEY]"),
        "bestdebrid_enabled": bool(settings.BESTDEBRID_API_KEY and settings.BESTDEBRID_API_KEY != "[YOUR_KEY]")
    }
