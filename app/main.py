from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.db.database import init_db
from app.core.scheduler import start_scheduler
from app.core.config import settings
from app.api.endpoints import router as api_router

app = FastAPI(title=settings.APP_NAME)

@app.on_event("startup")
async def startup():
    await init_db()
    start_scheduler()

app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/")
async def read_root():
    return FileResponse("app/static/index.html")

# Include API routes
app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
