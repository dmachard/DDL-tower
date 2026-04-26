from typing import List
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from app.core.scheduler import run_scrapers
from app.core.scanner import DirectScanner

router = APIRouter()

class ScanRequest(BaseModel):
    urls: List[str]

class ExtractRequest(BaseModel):
    text: str

@router.post("/scan/force")
async def force_scan(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_scrapers)
    return {"message": "Full discovery scan manually triggered."}

@router.post("/scan/direct")
async def direct_scan(request: ScanRequest, background_tasks: BackgroundTasks):
    """
    Triggers a direct scan of one or more URLs.
    If single URL, returns results immediately.
    """
    scanner = DirectScanner()
    if len(request.urls) == 1:
        results = await scanner.scan_urls(request.urls)
        if results and "error" not in results[0]:
            res = results[0]
            return {
                "message": f"Found {res['total']} links ({res['new']} new) on page.",
                "total": res["total"],
                "new": res["new"]
            }
        elif results and "error" in results[0]:
            return {"message": f"Scan failed: {results[0]['error']}", "total": 0, "new": 0}
        return {"message": "No links found on this page.", "total": 0, "new": 0}
    
    background_tasks.add_task(scanner.scan_urls, request.urls)
    return {"message": f"Scanning {len(request.urls)} URLs in background..."}

@router.post("/scan/categories")
async def scan_categories(background_tasks: BackgroundTasks):
    from app.core.scheduler import run_categorization
    background_tasks.add_task(run_categorization)
    return {"message": "Categorization of unassigned links triggered."}

@router.post("/scan/extract")
async def extract_text(request: ExtractRequest):
    """
    Extracts links from raw text and processes them immediately.
    """
    scanner = DirectScanner()
    result = await scanner.scan_text(request.text)
    
    if not result:
        return {"message": "No links found in the text.", "total": 0, "new": 0}

    return {
        "message": f"Found {result['total_found']} links ({result['new_added']} new).",
        "total": result["total_found"],
        "new": result["new_added"]
    }
