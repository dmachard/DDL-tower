import re
import math
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from sqlalchemy.future import select
from sqlalchemy import func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DownloadLink, MediaMetadata, ScrapedURL
from app.core.config import settings
from app.core.utils import format_size

class ReleaseService:
    @staticmethod
    async def get_latest_scan_time(db: AsyncSession):
        """Retrieve the most recent scan timestamp from ScrapedURL table."""
        stmt = select(func.max(ScrapedURL.last_scraped))
        result = await db.execute(stmt)
        res = result.scalar()
        if res and res.tzinfo is None:
            return res.replace(tzinfo=timezone.utc)
        return res

    @staticmethod
    async def get_threshold(db: AsyncSession, recent: bool, hours: int = None):
        """Unified threshold calculation for novelty window."""
        if not recent:
            return None
        if hours:
            return datetime.now(timezone.utc) - timedelta(hours=hours)
        
        last_scan = await ReleaseService.get_latest_scan_time(db)
        if not last_scan:
            return None
        return last_scan - timedelta(minutes=settings.SCAN_INTERVAL_MINUTES * settings.SCAN_NOVELTY_MULTIPLIER)

    @staticmethod
    async def get_grouped_releases(
        db: AsyncSession,
        page: int = 1,
        limit: int = 20,
        q: str = None,
        category: str = None,
        source: str = None,
        resolution: str = None,
        year: int = None,
        network: str = None,
        recent: bool = False,
        hours: int = None,
        show_all: bool = True,
        local: bool = None
    ):
        """Returns grouped download links (releases) for movies and series."""
        threshold = await ReleaseService.get_threshold(db, recent, hours)

        # Base statement for groups
        stmt = select(
            func.lower(DownloadLink.title).label("lower_title"),
            func.max(DownloadLink.title).label("display_title"),
            func.max(DownloadLink.year).label("year"),
            DownloadLink.category,
            func.max(DownloadLink.last_checked).label("latest"),
            func.max(MediaMetadata.poster_path).label("poster_path"),
            func.max(MediaMetadata.plot_en).label("plot_en"),
            func.max(MediaMetadata.plot_fr).label("plot_fr"),
            func.max(MediaMetadata.rating).label("rating"),
            func.max(MediaMetadata.official_title).label("official_title"),
            func.max(MediaMetadata.title_fr).label("title_fr"),
            func.max(MediaMetadata.year).label("official_year"),
            func.coalesce(DownloadLink.imdb_id, MediaMetadata.imdb_id).label("imdb_id")
        ).where(DownloadLink.status == "alive")
        
        stmt = stmt.outerjoin(MediaMetadata, DownloadLink.imdb_id == MediaMetadata.imdb_id)
        
        if q:
            keywords = q.split()
            for kw in keywords:
                stmt = stmt.where(or_(
                    DownloadLink.title.ilike(f"%{kw}%"),
                    DownloadLink.filename.ilike(f"%{kw}%"),
                    MediaMetadata.official_title.ilike(f"%{kw}%"),
                    MediaMetadata.title_fr.ilike(f"%{kw}%")
                ))
        if category:
            stmt = stmt.where(DownloadLink.category == category)
        if source:
            stmt = stmt.where(DownloadLink.source_name == source)
        if resolution:
            if resolution == "2160p":
                stmt = stmt.where(DownloadLink.resolution.ilike("2160p") | 
                                  DownloadLink.resolution.ilike("4K") | 
                                  DownloadLink.resolution.ilike("4Klight") |
                                  DownloadLink.resolution.ilike("4KLIGHT"))
            else:
                stmt = stmt.where(DownloadLink.resolution == resolution)
        if year:
            stmt = stmt.where(or_(DownloadLink.year == year, MediaMetadata.year == year))
        if network:
            stmt = stmt.where(DownloadLink.network == network)
        if recent and threshold:
            stmt = stmt.where(DownloadLink.last_checked >= threshold)
        if local is not None:
            if local:
                stmt = stmt.where(or_(
                    DownloadLink.imdb_id == None,
                    DownloadLink.imdb_id == "N/A",
                    and_(
                        DownloadLink.imdb_id.like("local%"),
                        or_(
                            MediaMetadata.plot_fr == "Sortie Locale",
                            MediaMetadata.plot_fr == None,
                            MediaMetadata.plot_fr == "",
                            MediaMetadata.plot_en == "Local Release",
                            MediaMetadata.plot_en == None,
                            MediaMetadata.plot_en == ""
                        )
                    )
                ))
            else:
                stmt = stmt.where(and_(
                    DownloadLink.imdb_id != None,
                    DownloadLink.imdb_id != "N/A",
                    or_(
                        ~DownloadLink.imdb_id.like("local%"),
                        and_(
                            MediaMetadata.plot_fr != None,
                            MediaMetadata.plot_fr != "",
                            MediaMetadata.plot_fr != "Sortie Locale",
                            MediaMetadata.plot_en != None,
                            MediaMetadata.plot_en != "",
                            MediaMetadata.plot_en != "Local Release"
                        )
                    )
                ))
            
        stmt = stmt.group_by(
            func.coalesce(DownloadLink.imdb_id, func.lower(DownloadLink.title)), 
            func.coalesce(DownloadLink.imdb_id, DownloadLink.year), 
            DownloadLink.category
        )
        
        # Get total count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await db.execute(count_stmt)
        total = total_result.scalar() or 0
        
        # Paginate
        stmt = stmt.order_by(func.max(DownloadLink.last_checked).desc())
        stmt = stmt.offset((page - 1) * limit).limit(limit)
        
        result = await db.execute(stmt)
        groups = result.all()
        
        items = []
        for g in groups:
            g_lower_title, g_title, g_year, g_cat, g_latest, g_poster, g_plot_en, g_plot_fr, g_rating, g_official, g_title_fr, g_off_year, g_imdb = g
            if not g_title: continue
            
            # Select releases belonging to this group
            # We handle NULLs for year and category to ensure items without metadata still group correctly
            if g_imdb and not g_imdb.startswith('local'):
                rel_stmt = select(DownloadLink).where(
                    DownloadLink.imdb_id == g_imdb,
                    DownloadLink.status == "alive"
                )
            else:
                rel_stmt = select(DownloadLink).where(
                    func.lower(DownloadLink.title) == g_lower_title,
                    DownloadLink.status == "alive"
                )
                if g_year is not None:
                    rel_stmt = rel_stmt.where(DownloadLink.year == g_year)
                else:
                    rel_stmt = rel_stmt.where(DownloadLink.year == None)
                
                if g_cat:
                    rel_stmt = rel_stmt.where(DownloadLink.category == g_cat)
                else:
                    rel_stmt = rel_stmt.where(DownloadLink.category == None)
            
            # Sub-filtering logic: ALWAYS show all versions inside the expanded card
            # as per user request to remove the toggle.
            pass 

            rel_stmt = rel_stmt.order_by(DownloadLink.last_checked.desc())
            rel_result = await db.execute(rel_stmt)
            releases = rel_result.scalars().all()
            
            release_cards = {}
            for r in releases:
                sig = r.filename or ""
                sig = re.sub(r'[._ ](?:part|pt|vol|volume)[._ ]?\d+', '', sig, flags=re.I)
                sig = re.sub(r'[._ ](?:rar|zip|7z|html|mkv|mp4|avi)$', '', sig, flags=re.I)
                sig = re.sub(r'[._\s-]+', '.', sig).lower()
                
                card_key = (r.season, r.episode, r.resolution, r.language, r.source_name, r.quality, r.codec, r.network, r.v_quality)
                sub_key = sig
                
                if card_key not in release_cards:
                    is_new = False
                    if r.last_checked and threshold:
                        l_checked = r.last_checked.replace(tzinfo=timezone.utc) if r.last_checked.tzinfo is None else r.last_checked
                        is_new = l_checked >= threshold
     
                    release_cards[card_key] = {
                        "id": r.id,
                        "season": r.season, "episode": r.episode,
                        "resolution": r.resolution, "language": r.language,
                        "source": r.source_name, "quality": r.quality, "codec": r.codec,
                        "network": r.network, "v_quality": r.v_quality,
                        "source_url": r.source_url, "is_new": is_new, "last_checked": r.last_checked,
                        "sub_releases": {}
                    }
                
                card = release_cards[card_key]
                if sub_key not in card["sub_releases"]:
                    is_sub_new = False
                    if r.last_checked and threshold:
                        l_checked = r.last_checked.replace(tzinfo=timezone.utc) if r.last_checked.tzinfo is None else r.last_checked
                        is_sub_new = l_checked >= threshold
                    if is_sub_new: card["is_new"] = True
 
                    card["sub_releases"][sub_key] = {
                        "filename": r.filename, 
                        "title": r.title,
                        "raw_title": r.raw_title,
                        "is_new": is_sub_new,
                        "part_sizes": {}, "parts": []
                    }
                
                sub = card["sub_releases"][sub_key]
                if not any(p["url"] == r.url for p in sub["parts"]):
                    part_match = re.search(r'Part\s*(\d+)', r.filename or '', re.I)
                    part_num = int(part_match.group(1)) if part_match else 1
                    b = r.size_bytes or 0
                    if part_num not in sub["part_sizes"] or b > sub["part_sizes"][part_num]:
                        sub["part_sizes"][part_num] = b
                    
                    sub["parts"].append({
                        "id": r.id, "part": part_num, "size": r.size,
                        "size_bytes": r.size_bytes, "hoster": r.hoster, "url": r.url
                    })
            
            # Formatting
            resolutions_map = {}
            for card in release_cards.values():
                formatted_subs = []
                for sub in card["sub_releases"].values():
                    total_bytes = sum(sub["part_sizes"].values())
                    sub["parts"].sort(key=lambda x: x["part"])
                    formatted_subs.append({
                        "filename": sub["filename"], 
                        "title": sub.get("title"),
                        "raw_title": sub.get("raw_title"),
                        "is_new": sub["is_new"],
                        "total_bytes": total_bytes, "total_size": format_size(total_bytes),
                        "parts": sub["parts"]
                    })
                card["sub_releases"] = formatted_subs
                
                res = card["resolution"] or "HD"
                if res not in resolutions_map: resolutions_map[res] = []
                resolutions_map[res].append(card)
            
            for res in resolutions_map:
                resolutions_map[res].sort(key=lambda x: (
                    int(x["season"]) if x["season"] is not None and str(x["season"]).isdigit() else 0,
                    int(x["episode"]) if x["episode"] is not None and str(x["episode"]).isdigit() else 0
                ))

            group_latest = releases[0].last_checked if releases else None
            items.append({
                "title": g_title, "official_title": g_official, "year": g_off_year or g_year,
                "category": g_cat, "poster_path": g_poster, "plot_en": g_plot_en, "plot_fr": g_plot_fr,
                "title_fr": g_title_fr, "rating": g_rating, "imdb_id": g_imdb,
                "last_updated": group_latest.isoformat() if hasattr(group_latest, "isoformat") else group_latest,
                "resolutions": resolutions_map, "count": len(release_cards)
            })
            
        return {
            "items": items, "total": total, "page": page, "limit": limit,
            "pages": math.ceil(total / limit) if limit > 0 else 0
        }

release_service = ReleaseService()
