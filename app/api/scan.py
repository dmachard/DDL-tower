from typing import List
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from app.core.scheduler import run_scrapers
from app.core.scanner import DirectScanner

router = APIRouter()

class ScanRequest(BaseModel):
    urls: List[str]

@router.post("/scan/force")
async def force_scan(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_scrapers)
    return {"message": "Full discovery scan manually triggered."}

@router.post("/scan/direct")
async def direct_scan(request: ScanRequest, background_tasks: BackgroundTasks):
    """
    Triggers a direct scan of one or more URLs in the background.
    """
    scanner = DirectScanner()
    background_tasks.add_task(scanner.scan_urls, request.urls)
    return {"message": f"Scanning {len(request.urls)} URLs in background..."}

@router.post("/scan/categories")
async def scan_categories(background_tasks: BackgroundTasks):
    from app.core.scheduler import run_categorization
    background_tasks.add_task(run_categorization)
    return {"message": "Categorization of unassigned links triggered."}
