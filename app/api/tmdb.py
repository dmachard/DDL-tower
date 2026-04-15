import httpx
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import DownloadLink, MediaMetadata
from app.core.config import settings

router = APIRouter()

class IdentificationRequest(BaseModel):
    imdb_id: Optional[str] = None
    tmdb_id: Optional[int] = None
    title: Optional[str] = None
    year: Optional[int] = None
    category: str = "movie"
    lang: Optional[str] = None
    link_ids: List[int]

@router.get("/tmdb/search")
async def search_tmdb(query: str, type: str = "movie", lang: str = None):
    """
    Search TMDb for a title.
    """
    try:
        from app.services.tmdb import tmdb_service
        search_lang = lang or settings.DEFAULT_LANGUAGE
        if len(search_lang) == 2:
            search_lang = f"{search_lang}-{search_lang.upper()}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            search_params = {
                "api_key": tmdb_service.api_key,
                "query": query,
                "language": search_lang
            }
            
            endpoint = "search/movie" if type == "movie" else "search/tv"
            r = await client.get(f"{tmdb_service.base_url}/{endpoint}", params=search_params)
            r.raise_for_status()
            data = r.json()
            
            results = []
            for res in data.get("results", []):
                date_str = res.get("release_date") or res.get("first_air_date") or ""
                results.append({
                    "id": res.get("id"),
                    "title": res.get("title") or res.get("name"),
                    "year": date_str[:4] if date_str else "N/A",
                    "poster_path": f"https://image.tmdb.org/t/p/w200{res.get('poster_path')}" if res.get("poster_path") else None,
                    "overview": res.get("overview")
                })
            return results
    except Exception as e:
        print(f"[API] TMDb search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/releases/identify")
async def identify_release(req: IdentificationRequest, db: AsyncSession = Depends(get_db)):
    """
    Manually identify a release by providing an IMDb ID or searching TMDb.
    """
    try:
        from app.services.tmdb import tmdb_service
        
        # 1. Fetch metadata from TMDb
        res_data = None
        if req.imdb_id:
            res_data = await tmdb_service.fetch_metadata_by_imdb_id(req.imdb_id, media_type=req.category)
        elif req.tmdb_id:
            res_data = await tmdb_service.fetch_metadata_by_tmdb_id(req.tmdb_id, media_type=req.category)
        elif req.title:
            res_data = await tmdb_service.fetch_metadata(req.title, req.year, req.category, language=req.lang)
            
        if not res_data:
            raise HTTPException(status_code=404, detail="Could not find metadata for provided info")
            
        # 2. Update MediaMetadata or create if new
        imdb_id = res_data.get("imdb_id") or f"local_{res_data.get('official_title').replace(' ', '_').lower()}"
        
        stmt = select(MediaMetadata).where(MediaMetadata.imdb_id == imdb_id)
        existing_meta = (await db.execute(stmt)).scalar()
        
        if not existing_meta:
            existing_meta = MediaMetadata(
                imdb_id=imdb_id,
                official_title=res_data.get("official_title"),
                title_fr=res_data.get("title_fr"),
                year=res_data.get("year"),
                poster_path=None, 
                plot_en=res_data.get("plot_en"),
                plot_fr=res_data.get("plot_fr"),
                rating=res_data.get("rating")
            )
            db.add(existing_meta)
            await db.flush()
            
        p_url = res_data.get("poster_url")
        if p_url:
             existing_meta.poster_path = await tmdb_service.download_poster(existing_meta.imdb_id, p_url)

        # 3. Update all provided links
        stmt_links = select(DownloadLink).where(DownloadLink.id.in_(req.link_ids))
        links_res = await db.execute(stmt_links)
        links = links_res.scalars().all()
        
        for link in links:
            link.imdb_id = existing_meta.imdb_id
            if existing_meta.official_title:
                link.title = existing_meta.official_title
            if existing_meta.year:
                link.year = existing_meta.year
        
        await db.commit()
        return {"status": "success", "imdb_id": existing_meta.imdb_id}
    except Exception as e:
        print(f"[API] Identification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
