import re
import math
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from sqlalchemy.future import select
from sqlalchemy import func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DownloadLink, MediaMetadata, ScrapedURL
from app.core.config import settings
from app.core.utils import format_size

_BY_SOURCE_CACHE = {}
_BY_SOURCE_TTL = 30.0


class ReleaseService:
    @staticmethod
    def invalidate_cache():
        _BY_SOURCE_CACHE.clear()
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
    def _format_group_releases(releases, threshold):
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
                if is_sub_new:
                    card["is_new"] = True

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
                    "size_bytes": r.size_bytes, "hoster": r.hoster, "url": r.url,
                    "status": r.status
                })

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
            if res not in resolutions_map:
                resolutions_map[res] = []
            resolutions_map[res].append(card)

        for res in resolutions_map:
            resolutions_map[res].sort(key=lambda x: (
                int(x["season"]) if x["season"] is not None and str(x["season"]).isdigit() else 0,
                int(x["episode"]) if x["episode"] is not None and str(x["episode"]).isdigit() else 0
            ))

        return resolutions_map, len(release_cards)

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
        local: bool = None,
        include_total: bool = True
    ):
        """Returns grouped download links (releases) for movies and series."""
        threshold = await ReleaseService.get_threshold(db, recent, hours)
        novelty_threshold = threshold or await ReleaseService.get_threshold(db, True, hours)

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
        total = 0
        if include_total:
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

            resolutions_map, card_count = ReleaseService._format_group_releases(releases, novelty_threshold)
            group_latest = releases[0].last_checked if releases else None
            items.append({
                "title": g_title, "official_title": g_official, "year": g_off_year or g_year,
                "category": g_cat, "poster_path": g_poster, "plot_en": g_plot_en, "plot_fr": g_plot_fr,
                "title_fr": g_title_fr, "rating": g_rating, "imdb_id": g_imdb,
                "last_updated": group_latest.isoformat() if hasattr(group_latest, "isoformat") else group_latest,
                "resolutions": resolutions_map, "count": card_count
            })
            
        return {
            "items": items, "total": total, "page": page, "limit": limit,
            "pages": math.ceil(total / limit) if limit > 0 else 0
        }

    @staticmethod
    async def get_releases_by_source(
        db: AsyncSession,
        limit_per_source: int = 20,
        category: str = None,
        resolution: str = None,
        year: int = None,
        network: str = None,
        recent: bool = True,
        hours: int = None,
        local: bool = None
    ):
        """Returns grouped releases organized by source for horizontal carousel rows."""
        cache_key = (limit_per_source, category, resolution, year, network, recent, hours, local)
        now = time.monotonic()
        cached = _BY_SOURCE_CACHE.get(cache_key)
        if cached and (now - cached[0]) < _BY_SOURCE_TTL:
            return cached[1]

        threshold = await ReleaseService.get_threshold(db, recent, hours)
        novelty_threshold = threshold or await ReleaseService.get_threshold(db, True, hours)

        src_stmt = select(
            DownloadLink.source_name,
            DownloadLink.category,
            func.max(DownloadLink.last_checked).label("latest")
        ).where(
            DownloadLink.status == "alive",
            DownloadLink.source_name != None,
            DownloadLink.source_name != ""
        )

        if category:
            src_stmt = src_stmt.where(DownloadLink.category == category)
        if resolution:
            if resolution == "2160p":
                src_stmt = src_stmt.where(
                    DownloadLink.resolution.ilike("2160p") |
                    DownloadLink.resolution.ilike("4K") |
                    DownloadLink.resolution.ilike("4Klight") |
                    DownloadLink.resolution.ilike("4KLIGHT")
                )
            else:
                src_stmt = src_stmt.where(DownloadLink.resolution == resolution)
        if network:
            src_stmt = src_stmt.where(DownloadLink.network == network)
        if recent and threshold:
            src_stmt = src_stmt.where(DownloadLink.last_checked >= threshold)
        if year:
            src_stmt = src_stmt.outerjoin(MediaMetadata, DownloadLink.imdb_id == MediaMetadata.imdb_id)
            src_stmt = src_stmt.where(or_(DownloadLink.year == year, MediaMetadata.year == year))

        src_stmt = src_stmt.group_by(
            DownloadLink.source_name,
            DownloadLink.category
        ).order_by(func.max(DownloadLink.last_checked).desc())
        src_result = await db.execute(src_stmt)
        source_cats = [(row[0], row[1]) for row in src_result.all() if row[0]]

        rows = []
        total_items = 0

        if year is not None or local is not None:
            for src, cat in source_cats:
                res = await ReleaseService.get_grouped_releases(
                    db=db, page=1, limit=limit_per_source, category=cat, source=src,
                    resolution=resolution, year=year, network=network, recent=recent,
                    hours=hours, local=local, include_total=False
                )
                if res["items"]:
                    row_total = len(res["items"])
                    rows.append({"source": src, "category": cat, "total": row_total, "items": res["items"]})
                    total_items += row_total
        else:
            for src, cat in source_cats:
                # Fast index-ordered scan on newest rows per (source, category)
                q_stmt = select(DownloadLink).where(
                    DownloadLink.status == "alive",
                    DownloadLink.source_name == src,
                    DownloadLink.category == cat
                )
                if resolution:
                    if resolution == "2160p":
                        q_stmt = q_stmt.where(
                            DownloadLink.resolution.ilike("2160p") |
                            DownloadLink.resolution.ilike("4K") |
                            DownloadLink.resolution.ilike("4Klight") |
                            DownloadLink.resolution.ilike("4KLIGHT")
                        )
                    else:
                        q_stmt = q_stmt.where(DownloadLink.resolution == resolution)
                if network:
                    q_stmt = q_stmt.where(DownloadLink.network == network)
                if recent and threshold:
                    q_stmt = q_stmt.where(DownloadLink.last_checked >= threshold)

                q_stmt = q_stmt.order_by(DownloadLink.last_checked.desc()).limit(400)
                link_res = await db.execute(q_stmt)
                recent_links = link_res.scalars().all()
                if not recent_links:
                    continue

                grouped_map = {}
                ordered_keys = []
                for r in recent_links:
                    if not r.title:
                        continue
                    key = (
                        r.imdb_id if r.imdb_id else r.title.lower(),
                        r.imdb_id if r.imdb_id else r.year,
                        r.category
                    )
                    if key not in grouped_map:
                        if len(ordered_keys) >= limit_per_source:
                            continue
                        ordered_keys.append(key)
                        grouped_map[key] = {"rep": r, "links": []}
                    grouped_map[key]["links"].append(r)

                if not ordered_keys:
                    continue

                imdb_ids = [
                    grouped_map[k]["rep"].imdb_id
                    for k in ordered_keys
                    if grouped_map[k]["rep"].imdb_id and not grouped_map[k]["rep"].imdb_id.startswith("local")
                ]
                meta_by_imdb = {}
                links_by_imdb = {}
                if imdb_ids:
                    meta_res = await db.execute(select(MediaMetadata).where(MediaMetadata.imdb_id.in_(imdb_ids)))
                    for m in meta_res.scalars().all():
                        meta_by_imdb[m.imdb_id] = m

                    all_imdb_res = await db.execute(
                        select(DownloadLink)
                        .where(DownloadLink.imdb_id.in_(imdb_ids), DownloadLink.status == "alive")
                        .order_by(DownloadLink.last_checked.desc())
                    )
                    for al in all_imdb_res.scalars().all():
                        links_by_imdb.setdefault(al.imdb_id, []).append(al)

                items = []
                for k in ordered_keys:
                    rep = grouped_map[k]["rep"]
                    m = meta_by_imdb.get(rep.imdb_id)
                    rel_list = links_by_imdb.get(rep.imdb_id) or grouped_map[k]["links"]
                    resolutions_map, card_count = ReleaseService._format_group_releases(rel_list, novelty_threshold)
                    group_latest = rel_list[0].last_checked if rel_list else rep.last_checked
                    items.append({
                        "title": rep.title,
                        "official_title": m.official_title if m else None,
                        "year": (m.year if m and m.year else rep.year),
                        "category": rep.category,
                        "poster_path": m.poster_path if m else None,
                        "plot_en": m.plot_en if m else None,
                        "plot_fr": m.plot_fr if m else None,
                        "title_fr": m.title_fr if m else None,
                        "rating": m.rating if m else None,
                        "imdb_id": rep.imdb_id,
                        "last_updated": group_latest.isoformat() if hasattr(group_latest, "isoformat") else group_latest,
                        "resolutions": resolutions_map,
                        "count": card_count
                    })

                if items:
                    rows.append({"source": src, "category": cat, "total": len(items), "items": items})
                    total_items += len(items)

        payload = {"rows": rows, "total": total_items}
        if len(_BY_SOURCE_CACHE) > 32:
            _BY_SOURCE_CACHE.clear()
        _BY_SOURCE_CACHE[cache_key] = (time.monotonic(), payload)
        return payload

release_service = ReleaseService()
