import math
from fastapi import APIRouter, Depends, Query
from sqlalchemy.future import select
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import DownloadLink
from app.services.release_service import release_service

router = APIRouter()

@router.get("/links")
async def get_links(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    q: str = Query(None),
    category: str = Query(None),
    status: str = Query(None),
    recent: bool = Query(False),
    hours: int = Query(None)
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

    if recent:
        threshold = await release_service.get_threshold(db, recent, hours)
        if threshold:
            stmt = stmt.where(DownloadLink.last_checked >= threshold)
    
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
    category: str = Query(None),
    source: str = Query(None),
    resolution: str = Query(None),
    year: int = Query(None),
    network: str = Query(None),
    recent: bool = Query(False),
    hours: int = Query(None)
):
    """
    Returns grouped download links (releases) for movies and series.
    """
    return await release_service.get_grouped_releases(
        db, page, limit, q, category, source, resolution, year, network, recent, hours
    )
