from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.db.database import init_db
from app.core.scheduler import start_scheduler
from app.core.config import settings
from app.api import (
    config, downloads, releases, scan, stats, tmdb, rss, browser
)

app = FastAPI(title=settings.APP_NAME)

@app.on_event("startup")
async def startup():
    await init_db()
    
    # Resume active downloads from database in the background
    import asyncio
    from app.services.downloader import downloader_service
    asyncio.create_task(downloader_service.resume_active_downloads())
    
    start_scheduler()

import os
os.makedirs(settings.POSTER_DIR, exist_ok=True)
os.makedirs("data/error_dumps", exist_ok=True)

app.mount("/posters", StaticFiles(directory=settings.POSTER_DIR), name="posters")
app.mount("/static/error_dumps", StaticFiles(directory="data/error_dumps"), name="error_dumps")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/")
async def read_root():
    return FileResponse("app/static/index.html")

# Include API routes
app.include_router(config.router, prefix="/api", tags=["config"])
app.include_router(downloads.router, prefix="/api", tags=["downloads"])
app.include_router(releases.router, prefix="/api", tags=["releases"])
app.include_router(scan.router, prefix="/api", tags=["scan"])
app.include_router(stats.router, prefix="/api", tags=["stats"])
app.include_router(tmdb.router, prefix="/api", tags=["tmdb"])
app.include_router(rss.router, prefix="/api", tags=["rss"])
app.include_router(browser.router, prefix="/api", tags=["browser"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
