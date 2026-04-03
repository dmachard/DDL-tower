from fastapi import APIRouter, Depends, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, or_
from pydantic import BaseModel
from typing import List
from datetime import datetime, timezone, timedelta
import math
import re

from app.db.database import get_db
from app.db.models import DownloadLink, ScrapedURL
from app.core.scheduler import run_scrapers
from app.core.scanner import DirectScanner
from app.core.utils import parse_size, format_size

from app.core.config import settings
router = APIRouter(prefix="/api")

class ScanRequest(BaseModel):
    urls: List[str]

async def get_latest_scan_time(db: AsyncSession):
    """
    Retrieve the most recent scan timestamp from ScrapedURL table.
    """
    stmt = select(func.max(ScrapedURL.last_scraped))
    result = await db.execute(stmt)
    res = result.scalar()
    if res and res.tzinfo is None:
        return res.replace(tzinfo=timezone.utc)
    return res

@router.get("/links")
async def get_links(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    q: str = Query(None),
    category: str = Query(None),
    status: str = Query(None)
):
    """
    Returns download links with pagination and search.
    """
    stmt = select(DownloadLink)
    
    if q:
        search_filter = or_(
            DownloadLink.filename.ilike(f"%{q}%"),
            DownloadLink.title.ilike(f"%{q}%"),
            DownloadLink.url.ilike(f"%{q}%")
        )
        stmt = stmt.where(search_filter)
    
    if category:
        stmt = stmt.where(DownloadLink.category == category)
    
    if status:
        stmt = stmt.where(DownloadLink.status == status)
    
    # Get total count for pagination
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0
    
    # Get paginated items
    stmt = stmt.order_by(DownloadLink.last_checked.desc())
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    
    result = await db.execute(stmt)
    links = result.scalars().all()
    
    return {
        "items": links,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": math.ceil(total / limit) if limit > 0 else 0
    }

@router.get("/releases")
async def get_releases(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    q: str = Query(None),
    category: str = Query(None)
):
    """
    Returns grouped download links (releases) for movies and series.
    """
    # Base statement for groups
    stmt = select(
        DownloadLink.title,
        DownloadLink.year,
        DownloadLink.category,
        func.max(DownloadLink.last_checked).label("latest")
    ).where(DownloadLink.status == "alive")
    
    if q:
        stmt = stmt.where(DownloadLink.title.ilike(f"%{q}%"))
    
    if category:
        stmt = stmt.where(DownloadLink.category == category)
        
    stmt = stmt.group_by(DownloadLink.title, DownloadLink.year, DownloadLink.category)
    
    # Get total count of groups
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0
    
    # Paginate groups
    stmt = stmt.order_by(func.max(DownloadLink.last_checked).desc())
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    
    result = await db.execute(stmt)
    groups = result.all()
    
    # Calculate novelty threshold (multiplier from config)
    last_scan = await get_latest_scan_time(db)
    threshold = last_scan - timedelta(minutes=settings.SCAN_INTERVAL_MINUTES * settings.SCAN_NOVELTY_MULTIPLIER) if last_scan else None

    # For each group, fetch and aggregate its releases
    items = []
    for g_title, g_year, g_cat, g_latest in groups:
        if not g_title: continue
        
        rel_stmt = select(DownloadLink).where(
            DownloadLink.title == g_title,
            DownloadLink.year == g_year,
            DownloadLink.category == g_cat,
            DownloadLink.status == "alive"
        ).order_by(DownloadLink.last_checked.desc())
        
        rel_result = await db.execute(rel_stmt)
        releases = rel_result.scalars().all()
        
        # Secondary grouping by Release Card (Episode, Pack, or unique Movie release)
        release_cards = {}
        for r in releases:
            # Create a "release signature" by removing part indicators from filename
            sig = r.filename or ""
            sig = re.sub(r'[._ ]part\s*\d+', '', sig, flags=re.I)
            sig = re.sub(r'[._ ]pt\s*\d+', '', sig, flags=re.I)
            sig = re.sub(r'\.(rar|zip|7z|html)$', '', sig, flags=re.I)
            
            # Group key: (Season, Episode, Resolution, Language, Source, Signature)
            key = (r.season, r.episode, r.resolution, r.language, r.source_name, sig.lower())
            
            if key not in release_cards:
                is_new = False
                if r.last_checked and threshold:
                    l_checked = r.last_checked
                    if l_checked.tzinfo is None:
                        l_checked = l_checked.replace(tzinfo=timezone.utc)
                    is_new = l_checked >= threshold

                release_cards[key] = {
                    "id": r.id,
                    "season": r.season,
                    "episode": r.episode,
                    "resolution": r.resolution,
                    "language": r.language,
                    "source": r.source_name,
                    "source_url": r.source_url,
                    "total_bytes": 0,
                    "last_checked": r.last_checked,
                    "is_new": is_new,
                    "parts": []
                }
            
            # Sum size and add part
            b = r.size_bytes or parse_size(r.size)
            release_cards[key]["total_bytes"] += b
            
            # Detect part number
            part_match = re.search(r'Part\s*(\d+)', r.filename, re.I)
            part_num = int(part_match.group(1)) if part_match else 1
            
            release_cards[key]["parts"].append({
                "id": r.id,
                "part": part_num,
                "size": r.size,
                "size_bytes": r.size_bytes,
                "hoster": r.hoster,
                "url": r.url
            })
            
        # Final formatting for the title group
        release_items = []
        for card in release_cards.values():
            card["parts"].sort(key=lambda x: x["part"])
            card["total_size"] = format_size(card["total_bytes"])
            release_items.append(card)

        # Group cards by resolution
        resolutions_map = {}
        for card in release_cards.values():
            res = card["resolution"] or "HD"
            if res not in resolutions_map:
                resolutions_map[res] = []
            resolutions_map[res].append(card)
        
        # Sort each resolution list by season/episode (ensure we handle potential string/int mix)
        for res in resolutions_map:
            resolutions_map[res].sort(key=lambda x: (
                int(x["season"]) if x["season"] is not None and str(x["season"]).isdigit() else 0,
                int(x["episode"]) if x["episode"] is not None and str(x["episode"]).isdigit() else 0
            ))

        items.append({
            "title": g_title,
            "year": g_year,
            "category": g_cat,
            "last_updated": g_latest,
            "resolutions": resolutions_map,
            "count": len(release_cards)
        })
        
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": math.ceil(total / limit) if limit > 0 else 0
    }

@router.get("/scraped")
async def get_scraped(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    q: str = Query(None)
):
    """
    Returns scraped URLs history with pagination and search.
    """
    stmt = select(ScrapedURL)
    
    if q:
        search_filter = or_(
            ScrapedURL.url.ilike(f"%{q}%"),
            ScrapedURL.source_name.ilike(f"%{q}%")
        )
        stmt = stmt.where(search_filter)
        
    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0
    
    # Get paginated items
    stmt = stmt.order_by(ScrapedURL.last_scraped.desc())
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    
    result = await db.execute(stmt)
    scraped = result.scalars().all()
    
    return {
        "items": scraped,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": math.ceil(total / limit) if limit > 0 else 0
    }

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

@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """
    Returns global statistics using optimized SQL aggregation.
    """
    # Unique Movies (Unique titles)
    movie_unique_stmt = select(func.count(func.distinct(DownloadLink.title))).where(DownloadLink.category == "movie")
    movie_unique_res = await db.execute(movie_unique_stmt)
    unique_movies = movie_unique_res.scalar() or 0
    
    # Total Movie Links
    movie_links_stmt = select(func.count(DownloadLink.id)).where(DownloadLink.category == "movie")
    movie_links_res = await db.execute(movie_links_stmt)
    links_movies = movie_links_res.scalar() or 0
    
    # Unique Series (Unique titles)
    series_unique_stmt = select(func.count(func.distinct(DownloadLink.title))).where(DownloadLink.category == "series")
    series_unique_res = await db.execute(series_unique_stmt)
    unique_series = series_unique_res.scalar() or 0
    
    # Total Series Links
    series_links_stmt = select(func.count(DownloadLink.id)).where(DownloadLink.category == "series")
    series_links_res = await db.execute(series_links_stmt)
    links_series = series_links_res.scalar() or 0
    
    # Total links
    total_links_stmt = select(func.count(DownloadLink.id))
    total_links_res = await db.execute(total_links_stmt)
    total_links = total_links_res.scalar() or 0
    
    # Stats by source
    stmt = select(DownloadLink.source_name, DownloadLink.size)
    result = await db.execute(stmt)
    rows = result.all()
    
    size_by_source = {}
    total_size_bytes = 0
    
    for source, size_str in rows:
        source_name = source or "Unknown"
        bytes_val = parse_size(size_str)
        size_by_source[source_name] = size_by_source.get(source_name, 0) + bytes_val
        total_size_bytes += bytes_val
        
    # Format sizes back to string
    fmt_size_by_source = {src: format_size(val) for src, val in size_by_source.items()}
    
    # Dead links
    dead_links_stmt = select(func.count(DownloadLink.id)).where(DownloadLink.status == "dead")
    dead_links_res = await db.execute(dead_links_stmt)
    dead_links = dead_links_res.scalar() or 0
    
    stats = {
        "unique_movies": unique_movies,
        "unique_series": unique_series,
        "links_movies": links_movies,
        "links_series": links_series,
        "total_movies": links_movies,  # Backwards compatibility
        "total_series": links_series,  # Backwards compatibility
        "total_links": total_links,
        "dead_links": dead_links,
        "total_size": format_size(total_size_bytes),
        "total_size_bytes": total_size_bytes,
        "size_by_source": fmt_size_by_source,
        "size_by_source_raw": size_by_source
    }
    return stats
