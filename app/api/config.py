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
        "alldebrid_enabled": bool(settings.ALLDEBRID_API_KEY)
    }
