import json
import os
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select, update, delete, func, or_, and_
from app.db.database import AsyncSessionLocal
from app.db.models import DownloadLink, ScrapedURL, MediaMetadata
from app.services.parser_service import parser_service
from app.services.enrichment_service import enrichment_service
from app.services.tmdb import tmdb_service
from app.services.translation import translation_service
from app.core.config import settings
from pathlib import Path
import html
import re

async def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

class MaintenanceService:
    @staticmethod
    async def backup_db(output_path: str = "data/backup.json"):
        async with AsyncSessionLocal() as session:
            stmt_links = select(DownloadLink)
            result_links = await session.execute(stmt_links)
            links = result_links.scalars().all()
            
            stmt_scraped = select(ScrapedURL)
            result_scraped = await session.execute(stmt_scraped)
            scraped = result_scraped.scalars().all()
            
            data = {
                "download_links": [
                    {c.name: getattr(link, c.name) for c in DownloadLink.__table__.columns} 
                    for link in links
                ],
                "scraped_urls": [
                    {c.name: getattr(url, c.name) for c in ScrapedURL.__table__.columns}
                    for url in scraped
                ],
                "backup_date": datetime.now(timezone.utc).isoformat()
            }
            
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, default=json_serial, ensure_ascii=False)
            return len(links), len(scraped)

    @staticmethod
    async def restore_db(input_path: str = "data/backup.json"):
        if not os.path.exists(input_path):
            return None, None

        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        def parse_dt(s):
            if not s: return None
            return datetime.fromisoformat(s.replace('Z', '+00:00'))

        async with AsyncSessionLocal() as session:
            scraped_count = 0
            for entry_data in data.get("scraped_urls", []):
                if "last_scraped" in entry_data and entry_data["last_scraped"]:
                    entry_data["last_scraped"] = parse_dt(entry_data["last_scraped"])
                
                model_keys = {c.name for c in ScrapedURL.__table__.columns}
                filtered_data = {k: v for k, v in entry_data.items() if k in model_keys}
                
                obj = ScrapedURL(**filtered_data)
                await session.merge(obj)
                scraped_count += 1
                
            links_count = 0
            for link_data in data.get("download_links", []):
                if "last_checked" in link_data and link_data["last_checked"]:
                    link_data["last_checked"] = parse_dt(link_data["last_checked"])
                
                model_keys = {c.name for c in DownloadLink.__table__.columns}
                filtered_data = {k: v for k, v in link_data.items() if k in model_keys}
                
                obj = DownloadLink(**filtered_data)
                await session.merge(obj)
                links_count += 1

            await session.commit()
            return links_count, scraped_count

    @staticmethod
    async def harmonize_titles():
        async with AsyncSessionLocal() as session:
            stmt = select(
                func.lower(DownloadLink.title).label("lower_group"),
                DownloadLink.title,
                MediaMetadata.official_title
            ).outerjoin(
                MediaMetadata, DownloadLink.imdb_id == MediaMetadata.imdb_id
            )
            result = await session.execute(stmt)
            rows = result.all()
            
            group_winners = {}
            for lower_title, current_title, official_title in rows:
                if not lower_title: continue
                existing_winner = group_winners.get(lower_title)
                if official_title:
                    group_winners[lower_title] = official_title
                elif not existing_winner:
                    group_winners[lower_title] = current_title.title() if current_title else lower_title.title()

            total_updated = 0
            for lower_title, winner in group_winners.items():
                stmt_year = select(MediaMetadata.year).where(MediaMetadata.official_title == winner).limit(1)
                official_year = (await session.execute(stmt_year)).scalar()

                up_stmt = update(DownloadLink).where(func.lower(DownloadLink.title) == lower_title)
                up_stmt_title = up_stmt.where(DownloadLink.title != winner).values(title=winner)
                res_t = await session.execute(up_stmt_title)
                total_updated += res_t.rowcount
                
                if official_year:
                    up_stmt_year = up_stmt.where(DownloadLink.year != official_year).values(year=official_year)
                    res_y = await session.execute(up_stmt_year)
                    total_updated += res_y.rowcount

            await session.commit()
            return len(group_winners), total_updated

    @staticmethod
    async def audit_metadata():
        async with AsyncSessionLocal() as session:
            stmt_total = select(func.count()).select_from(
                select(DownloadLink.id).group_by(
                    func.coalesce(DownloadLink.imdb_id, func.lower(DownloadLink.title)),
                    func.coalesce(DownloadLink.imdb_id, DownloadLink.year),
                    DownloadLink.category
                ).subquery()
            )
            total = (await session.execute(stmt_total)).scalar() or 0
            
            stmt_untagged = select(func.count()).select_from(
                select(DownloadLink.id).where(DownloadLink.imdb_id == None).group_by(
                    func.lower(DownloadLink.title), DownloadLink.year, DownloadLink.category
                ).subquery()
            )
            untagged = (await session.execute(stmt_untagged)).scalar() or 0
            
            stmt_no_title_fr = select(func.count(MediaMetadata.imdb_id)).where(
                or_(MediaMetadata.title_fr == None, MediaMetadata.title_fr == "")
            )
            no_title_fr = (await session.execute(stmt_no_title_fr)).scalar() or 0

            stmt_no_plot = select(func.count(MediaMetadata.imdb_id)).where(
                or_(MediaMetadata.plot_fr == None, MediaMetadata.plot_fr == "")
            )
            no_plot = (await session.execute(stmt_no_plot)).scalar() or 0
            
            stmt_no_poster = select(func.count(MediaMetadata.imdb_id)).where(
                or_(MediaMetadata.poster_path == None, MediaMetadata.poster_path == "")
            )
            no_poster = (await session.execute(stmt_no_poster)).scalar() or 0
            
            stmt_list = select(
                DownloadLink.title, DownloadLink.year, DownloadLink.category, func.max(DownloadLink.last_checked)
            ).where(DownloadLink.imdb_id == None).group_by(
                func.lower(DownloadLink.title), DownloadLink.year, DownloadLink.category
            ).order_by(func.max(DownloadLink.last_checked).desc()).limit(10)
            
            recent_untagged = (await session.execute(stmt_list)).all()
            
            return {
                "total": total,
                "untagged": untagged,
                "no_title_fr": no_title_fr,
                "no_plot": no_plot,
                "no_poster": no_poster,
                "recent_untagged": recent_untagged
            }

    @staticmethod
    async def repair_media_metadata():
        """
        Scans MediaMetadata for missing fields and tries to re-fetch them.
        """
        async with AsyncSessionLocal() as session:
            stmt = select(MediaMetadata).where(
                or_(
                    MediaMetadata.poster_path == None,
                    MediaMetadata.poster_path == "",
                    MediaMetadata.title_fr == None,
                    MediaMetadata.title_fr == "",
                    MediaMetadata.plot_fr == None,
                    MediaMetadata.plot_fr == "",
                    MediaMetadata.rating == None,
                    MediaMetadata.rating == "",
                    MediaMetadata.year == None,
                    MediaMetadata.imdb_id == "N/A",
                    and_(MediaMetadata.official_title == MediaMetadata.title_fr, MediaMetadata.title_fr != None, MediaMetadata.title_fr != "")
                )
            )
            result = await session.execute(stmt)
            to_repair = result.scalars().all()
            
            # Watchdog for posters on disk
            stmt_all = select(MediaMetadata).where(MediaMetadata.poster_path != None, MediaMetadata.poster_path != "")
            all_with_posters = (await session.execute(stmt_all)).scalars().all()
            
            for meta in all_with_posters:
                p_filename = os.path.basename(meta.poster_path)
                p_disk_path = Path(settings.POSTER_DIR) / p_filename
                if not p_disk_path.exists():
                    meta.poster_path = None
                    if meta not in to_repair: to_repair.append(meta)
                elif "static/posters/" in meta.poster_path:
                    meta.poster_path = meta.poster_path.replace("static/posters/", "posters/")
            
            await session.commit()
            
            if not to_repair: return
            
            for meta in to_repair:
                try:
                    clean_title = parser_service.clean_search_title(meta.official_title)
                    res_data = await tmdb_service.fetch_metadata_by_imdb_id(meta.imdb_id, clean_title, meta.year)
                    if not res_data:
                        if meta.poster_path is None: meta.poster_path = ""
                        if meta.title_fr is None: meta.title_fr = ""
                        if meta.plot_fr is None: meta.plot_fr = ""
                        if meta.rating is None: meta.rating = ""
                        await session.commit()
                        continue
                    
                    if not meta.poster_path:
                        p_url = res_data.get("poster_url")
                        if p_url and p_url != "N/A":
                            meta.poster_path = await tmdb_service.download_poster(meta.imdb_id, p_url)
                        else: meta.poster_path = ""
                    
                    if not meta.plot_fr:
                        plot_en = res_data.get("plot_en") or res_data.get("plot")
                        plot_fr = res_data.get("plot_fr")
                        if plot_en and not plot_fr:
                            plot_fr = await translation_service.translate(plot_en)
                        meta.plot_fr = plot_fr or ""
                    
                    if not meta.title_fr: meta.title_fr = res_data.get("title_fr") or ""
                    if not meta.rating: meta.rating = res_data.get("rating") or ""
                    if not meta.year: meta.year = res_data.get("year")
                    
                    await session.commit()
                except Exception as e:
                    print(f"[MAINTENANCE] Repair error for {meta.imdb_id}: {e}")

    @staticmethod
    async def repair_links_tech_metadata():
        """
        Scans DownloadLinks for missing technical metadata and re-parses them.
        """
        async with AsyncSessionLocal() as session:
            stmt = select(DownloadLink).where(
                (DownloadLink.filename != None),
                or_(
                    DownloadLink.imdb_id == None,
                    DownloadLink.imdb_id == "N/A",
                    DownloadLink.network == None,
                    DownloadLink.network == "",
                    DownloadLink.v_quality == None,
                    DownloadLink.v_quality == "",
                    DownloadLink.title.ilike("%&#%"),
                    DownloadLink.title.ilike("% part%"),
                    DownloadLink.title.ilike("%.part%"),
                    DownloadLink.title.ilike("% vol%"),
                    DownloadLink.title.ilike("%.vol%")
                )
            )
            result = await session.execute(stmt)
            to_repair = result.scalars().all()
            
            if not to_repair: return
            
            for link in to_repair:
                old_title = link.title
                if link.title: link.title = html.unescape(link.title)
                p = parser_service.parse_filename(link.filename)
                if p:
                    if p["title"]: link.title = p["title"]
                    link.network = p["network"] or ""
                    link.v_quality = p["v_quality"] or ""
                    if not link.codec: link.codec = p["codec"]
                    if not link.quality: link.quality = p["quality"]
                    if not link.resolution: link.resolution = p["resolution"]
                
                # If title changed and we have a local ID, we must reset it so enrichment regenerates it correctly
                if link.title != old_title and link.imdb_id and link.imdb_id.startswith("local_"):
                    link.imdb_id = None

                if link.imdb_id and not link.imdb_id.startswith("local_"):
                    stmt_m = select(MediaMetadata).where(MediaMetadata.imdb_id == link.imdb_id)
                    meta = (await session.execute(stmt_m)).scalar()
                    if meta:
                        if meta.official_title and link.title != meta.official_title:
                            link.title = meta.official_title
                        if meta.year: link.year = meta.year

            await session.commit()
            
            # Retry enrichment for missing IDs or those we just reset
            missing = [l for l in to_repair if not l.imdb_id or l.imdb_id == "N/A"]
            if missing:
                await enrichment_service.process_batch(session, missing)
                await session.commit()

    @staticmethod
    async def repair_download_history():
        """
        Enriches missing metadata and removes duplicates in the download history.
        """
        from app.db.models import DownloadHistory, MediaMetadata
        from app.core.utils import normalize_title
        from app.services.parser_service import parser_service
        from sqlalchemy import select, delete

        print("[MAINTENANCE] Running repair on DownloadHistory...")
        async with AsyncSessionLocal() as session:
            # 1. Fetch all download history entries
            stmt = select(DownloadHistory)
            res = await session.execute(stmt)
            history_entries = res.scalars().all()
            
            # 2. Fetch all media metadata for matching
            stmt_meta = select(MediaMetadata)
            res_meta = await session.execute(stmt_meta)
            all_metadata = res_meta.scalars().all()
            
            # Pre-index metadata by normalized titles
            meta_by_norm_title = {}
            for meta in all_metadata:
                norm_titles = []
                if meta.official_title:
                    norm_titles.append(normalize_title(meta.official_title))
                if meta.title_fr:
                    norm_titles.append(normalize_title(meta.title_fr))
                
                for nt in norm_titles:
                    if nt:
                        if nt not in meta_by_norm_title:
                            meta_by_norm_title[nt] = []
                        meta_by_norm_title[nt].append(meta)
            
            updated_count = 0
            # Enrich missing metadata in history
            for entry in history_entries:
                if not entry.imdb_id or entry.imdb_id == "N/A" or entry.imdb_id.startswith("local_"):
                    # Try to parse and match
                    parsed = parser_service.parse_filename(entry.title)
                    clean_title = parsed.get("title", entry.title) if entry.title else ""
                    norm_entry_title = normalize_title(clean_title)
                    entry_year = entry.year or parsed.get("year")
                    
                    if norm_entry_title in meta_by_norm_title:
                        # Find the best metadata match (matching year if possible)
                        candidates = meta_by_norm_title[norm_entry_title]
                        matched_meta = None
                        if entry_year:
                            for cand in candidates:
                                if cand.year == entry_year:
                                    matched_meta = cand
                                    break
                        if not matched_meta:
                            # Fallback to the first candidate if no year match
                            matched_meta = candidates[0]
                            
                        if matched_meta:
                            entry.imdb_id = matched_meta.imdb_id
                            if matched_meta.title_fr:
                                entry.title = matched_meta.title_fr
                            elif matched_meta.official_title:
                                entry.title = matched_meta.official_title
                            
                            if matched_meta.year:
                                entry.year = matched_meta.year
                            elif entry_year:
                                entry.year = entry_year
                                
                            updated_count += 1

            if updated_count > 0:
                await session.commit()
                print(f"[MAINTENANCE] Enriched {updated_count} history entries.")
                
            # 3. Deduplicate history
            # Re-fetch entries to have updated metadata
            stmt = select(DownloadHistory).order_by(DownloadHistory.download_date.desc())
            res = await session.execute(stmt)
            history_entries = res.scalars().all()
            
            seen_keys = set()
            deleted_ids = []
            
            for entry in history_entries:
                # Key can be:
                # - (imdb_id, season, episode) if imdb_id is available
                # - (normalized_title, year, season, episode) otherwise
                parsed = parser_service.parse_filename(entry.title)
                clean_title = parsed.get("title", entry.title) if entry.title else ""
                norm_title = normalize_title(clean_title)
                year = entry.year or parsed.get("year")
                
                # Normalize season/episode values
                def norm_se(val):
                    if not val: return ""
                    try:
                        return str(int(val)).zfill(2)
                    except:
                        return str(val).strip().upper()
                
                s_str = norm_se(entry.season)
                e_str = norm_se(entry.episode)
                
                if entry.imdb_id and not entry.imdb_id.startswith("local_"):
                    key = (entry.imdb_id, s_str, e_str)
                else:
                    key = (norm_title, year, s_str, e_str)
                
                if key in seen_keys:
                    deleted_ids.append(entry.id)
                else:
                    seen_keys.add(key)
            
            if deleted_ids:
                del_stmt = delete(DownloadHistory).where(DownloadHistory.id.in_(deleted_ids))
                await session.execute(del_stmt)
                await session.commit()
                print(f"[MAINTENANCE] Deleted {len(deleted_ids)} duplicate history entries.")
                return updated_count, len(deleted_ids)
            
            return updated_count, 0

maintenance_service = MaintenanceService()

