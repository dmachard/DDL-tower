from fastapi import APIRouter
from app.services.browser_manager import browser_manager

router = APIRouter()

@router.post("/browser/restart")
async def restart_browser():
    """
    Manually forces a restart of the remote Chromium browser and its proxy.
    Useful when Playwright gets stuck or crashes due to service worker issues.
    """
    print("[API] Manual browser restart requested.")
    await browser_manager.restart_browser()
    return {"message": "Browser successfully restarted and cleared."}
