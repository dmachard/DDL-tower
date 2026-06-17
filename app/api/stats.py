from fastapi import APIRouter, Depends
from sqlalchemy.future import select
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import DownloadLink, ScrapedURL, MediaMetadata
from app.core.config import settings
from app.core.utils import parse_size, format_size

router = APIRouter()

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
        "total_movies": links_movies,
        "total_series": links_series,
        "total_links": total_links,
        "dead_links": dead_links,
        "total_size": format_size(total_size_bytes),
        "total_size_bytes": total_size_bytes,
        "size_by_source": fmt_size_by_source,
        "size_by_source_raw": size_by_source
    }
    return stats

@router.get("/sources/dashboard")
async def get_sources_dashboard(db: AsyncSession = Depends(get_db)):
    """
    Returns a detailed dashboard of all sources, their health and last additions.
    """
    configured_sources = {s["name"]: s.get("entry_url") for s in settings.SCRAPER_SOURCES}
    
    source_stats_stmt = select(
        DownloadLink.source_name,
        func.count(DownloadLink.id).label("count"),
        func.max(DownloadLink.last_checked).label("last_checked")
    ).group_by(DownloadLink.source_name)
    
    res_stats = await db.execute(source_stats_stmt)
    db_stats = {r.source_name: {"count": r.count, "last_checked": r.last_checked} for r in res_stats.all()}
    
    sources_dashboard = []
    all_names = sorted(list(set(configured_sources.keys()) | set(db_stats.keys())))
    
    for name in all_names:
        if name == "Unknown" or not name: continue
        
        entry_url = configured_sources.get(name)
        if not entry_url:
            last_scraped_stmt = select(ScrapedURL.url).where(ScrapedURL.source_name == name).order_by(ScrapedURL.last_scraped.desc()).limit(1)
            entry_url = (await db.execute(last_scraped_stmt)).scalar()

        last_link_stmt = select(DownloadLink).where(DownloadLink.source_name == name).order_by(DownloadLink.last_checked.desc()).limit(1)
        last_link = (await db.execute(last_link_stmt)).scalar()
        
        last_scan_stmt = select(ScrapedURL).where(ScrapedURL.source_name == name).order_by(ScrapedURL.last_scraped.desc()).limit(1)
        last_scan = (await db.execute(last_scan_stmt)).scalar()
        
        sources_dashboard.append({
            "name": name,
            "entry_url": entry_url,
            "total_items": db_stats.get(name, {}).get("count", 0),
            "last_scan": last_scan.last_scraped.isoformat() if last_scan else None,
            "last_status": last_scan.status if last_scan else "unknown",
            "last_item": {
                "title": last_link.title if last_link else None,
                "url": last_link.source_url if last_link else None,
                "date": last_link.last_checked.isoformat() if last_link else None
            } if last_link else None
        })
        
    return {"sources": sources_dashboard}

@router.get("/sources")
async def get_sources(db: AsyncSession = Depends(get_db)):
    """
    Returns a list of unique source names from the database.
    """
    stmt = select(func.distinct(DownloadLink.source_name)).where(DownloadLink.source_name != None)
    result = await db.execute(stmt)
    sources = result.scalars().all()
    return sorted([s for s in sources if s])

@router.get("/years")
async def get_years(db: AsyncSession = Depends(get_db)):
    """
    Returns a list of unique years from both DownloadLink and MediaMetadata.
    """
    stmt_dl = select(func.distinct(DownloadLink.year)).where(DownloadLink.year != None)
    stmt_meta = select(func.distinct(MediaMetadata.year)).where(MediaMetadata.year != None)
    
    res_dl = await db.execute(stmt_dl)
    res_meta = await db.execute(stmt_meta)
    
    years = set(res_dl.scalars().all()) | set(res_meta.scalars().all())
    return sorted([y for y in years if y], reverse=True)

@router.get("/networks")
async def get_networks(db: AsyncSession = Depends(get_db)):
    """
    Returns a list of unique network names from the database.
    """
    stmt = select(func.distinct(DownloadLink.network)).where(DownloadLink.network != None)
    result = await db.execute(stmt)
    networks = result.scalars().all()
    return sorted([n for n in networks if n])

@router.get("/errors")
async def get_errors(db: AsyncSession = Depends(get_db)):
    """
    Returns the list of scraping errors.
    """
    stmt = select(ScrapedURL).where(ScrapedURL.status.like("failed%")).order_by(ScrapedURL.last_scraped.desc()).limit(100)
    result = await db.execute(stmt)
    errors = result.scalars().all()
    
    return [{
        "url": e.url,
        "source": e.source_name,
        "date": e.last_scraped.isoformat(),
        "error": e.status.replace("failed: ", "") if e.status.startswith("failed: ") else e.status,
        "screenshot_path": e.screenshot_path,
        "html_path": e.html_path
    } for e in errors]

@router.delete("/errors")
async def clear_errors(db: AsyncSession = Depends(get_db)):
    import os
    from sqlalchemy import update
    
    # 1. Fetch paths first to clean up files on disk
    stmt_select = select(ScrapedURL).where(ScrapedURL.status.like("failed%"))
    result = await db.execute(stmt_select)
    records = result.scalars().all()
    
    for r in records:
        if r.screenshot_path:
            path_data = r.screenshot_path.lstrip('/')
            if path_data.startswith("static/error_dumps/"):
                path_data = path_data.replace("static/error_dumps/", "data/error_dumps/")
            path_app = r.screenshot_path.lstrip('/')
            if path_app.startswith("static/"):
                path_app = "app/" + path_app
            for p in (path_data, path_app):
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except Exception as e:
                    print(f"[DB] Error removing screenshot file {p}: {e}")
                
        if r.html_path:
            path_data = r.html_path.lstrip('/')
            if path_data.startswith("static/error_dumps/"):
                path_data = path_data.replace("static/error_dumps/", "data/error_dumps/")
            path_app = r.html_path.lstrip('/')
            if path_app.startswith("static/"):
                path_app = "app/" + path_app
            for p in (path_data, path_app):
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except Exception as e:
                    print(f"[DB] Error removing HTML dump file {p}: {e}")

    # 2. Mark errors as ignored and clear paths in DB
    stmt = update(ScrapedURL).where(ScrapedURL.status.like("failed%")).values(
        status="ignored",
        screenshot_path=None,
        html_path=None
    )
    await db.execute(stmt)
    await db.commit()
    return {"message": "Errors cleared"}
