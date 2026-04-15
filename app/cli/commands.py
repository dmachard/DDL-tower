import asyncio
from typing import Optional
import json
import os
import re
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update, delete, func, or_, String
from sqlalchemy.inspection import inspect

from app.db.database import AsyncSessionLocal
from app.db.models import DownloadLink, ScrapedURL, MediaMetadata
from app.core.categorization import Categorizer
from app.core.hoster import Hoster
from app.core.utils import parse_size, format_size

def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

class DBCommands:
    @staticmethod
    async def backup(output_path: str = "data/backup.json"):
        print(f"--- [DB] Exporting database to {output_path} ---")
        async with AsyncSessionLocal() as session:
            # 1. Fetch Links
            stmt_links = select(DownloadLink)
            result_links = await session.execute(stmt_links)
            links = result_links.scalars().all()
            
            # 2. Fetch Scraped URLs
            stmt_scraped = select(ScrapedURL)
            result_scraped = await session.execute(stmt_scraped)
            scraped = result_scraped.scalars().all()
            
            # Structure the data
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
                
            print(f"SUCCESS: Exported {len(links)} links and {len(scraped)} history entries.")

    @staticmethod
    async def restore(input_path: str = "data/backup.json"):
        print(f"--- [DB] Restoring database from {input_path} ---")
        if not os.path.exists(input_path):
            print(f"ERROR: Backup file {input_path} not found.")
            return

        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        def parse_dt(s):
            if not s: return None
            return datetime.fromisoformat(s.replace('Z', '+00:00'))

        async with AsyncSessionLocal() as session:
            # 1. Restore Scraped URLs
            scraped_count = 0
            for entry_data in data.get("scraped_urls", []):
                if "last_scraped" in entry_data and entry_data["last_scraped"]:
                    entry_data["last_scraped"] = parse_dt(entry_data["last_scraped"])
                
                model_keys = {c.name for c in ScrapedURL.__table__.columns}
                filtered_data = {k: v for k, v in entry_data.items() if k in model_keys}
                
                obj = ScrapedURL(**filtered_data)
                await session.merge(obj)
                scraped_count += 1
                
            # 2. Restore Download Links
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
            print(f"SUCCESS: Restored {links_count} links and {scraped_count} history entries.")

    @staticmethod
    async def reset_scans(pattern: str = None):
        print(f"--- [DB] Resetting scan history (Pattern: {pattern or 'ALL'}) ---")
        async with AsyncSessionLocal() as session:
            stmt = delete(ScrapedURL)
            if pattern:
                stmt = stmt.where(ScrapedURL.url.ilike(f"%{pattern}%"))
            
            result = await session.execute(stmt)
            await session.commit()
            print(f"SUCCESS: {result.rowcount} entries removed from scraping history.")

    @staticmethod
    async def reset_metadata(title: str = None, imdb_id: str = None):
        print(f"--- [DB] Resetting metadata (Title: {title}, ID: {imdb_id}) ---")
        if not title and not imdb_id:
            print("ERROR: You must provide --title or --id.")
            return

        async with AsyncSessionLocal() as session:
            # 1. Clear imdb_id in download_links
            stmt = update(DownloadLink).values(imdb_id=None).where(DownloadLink.imdb_id != None)
            
            if title:
                stmt = stmt.where(DownloadLink.title.ilike(f"%{title}%"))
            if imdb_id:
                stmt = stmt.where(DownloadLink.imdb_id == imdb_id)
                
            result = await session.execute(stmt)
            affected = result.rowcount
            
            # 2. Cleanup MediaMetadata
            if title:
                del_stmt = delete(MediaMetadata).where(MediaMetadata.official_title.ilike(f"%{title}%"))
                await session.execute(del_stmt)
            if imdb_id:
                del_stmt = delete(MediaMetadata).where(MediaMetadata.imdb_id == imdb_id)
                await session.execute(del_stmt)

            await session.commit()
            print(f"SUCCESS: Reset {affected} links. Central metadata cleaned.")
            
    @staticmethod
    async def cleanup():
        print("--- [DB] Global Title Harmonization ---")
        async with AsyncSessionLocal() as session:
            # 1. Fetch all links to group them in memory by lowercase title
            # We also fetch official_title to find the best candidate
            stmt = select(
                func.lower(DownloadLink.title).label("lower_group"),
                DownloadLink.title,
                MediaMetadata.official_title
            ).outerjoin(
                MediaMetadata, DownloadLink.imdb_id == MediaMetadata.imdb_id
            )
            
            result = await session.execute(stmt)
            rows = result.all()
            
            # 2. Identify the best title candidate for each lowercase group
            group_winners = {} # lower_title -> best_casing
            for lower_title, current_title, official_title in rows:
                if not lower_title: continue
                
                # Winner priority: 
                # 1. Official title from metadata
                # 2. Already established winner (if it was official)
                # 3. Current title (if winner doesn't exist yet or is just a guess)
                
                existing_winner = group_winners.get(lower_title)
                
                # If we have an official title, it's the absolute winner
                if official_title:
                    group_winners[lower_title] = official_title
                elif not existing_winner:
                    # Fallback to Title Case if no winner yet
                    group_winners[lower_title] = current_title.title() if current_title else lower_title.title()

            # 3. Update all links that don't match their group winner
            print(f"[DB] Found {len(group_winners)} unique title groups. Harmonizing...")
            
            total_updated = 0
            for lower_title, winner in group_winners.items():
                # Fetch official year if available from metadata for this group
                stmt_year = select(MediaMetadata.year).where(
                    MediaMetadata.official_title == winner
                ).limit(1)
                official_year = (await session.execute(stmt_year)).scalar()

                up_stmt = update(DownloadLink).where(
                    func.lower(DownloadLink.title) == lower_title
                )
                
                # Update title if different
                up_stmt_title = up_stmt.where(DownloadLink.title != winner).values(title=winner)
                res_t = await session.execute(up_stmt_title)
                
                # Update year if we have an official one and it's missing or different
                if official_year:
                    up_stmt_year = up_stmt.where(DownloadLink.year != official_year).values(year=official_year)
                    res_y = await session.execute(up_stmt_year)
                    total_updated += res_y.rowcount

                total_updated += res_t.rowcount
            
            await session.commit()
            print(f"\nSUCCESS: Harmonized {total_updated} link fields (titles/years).")

    @staticmethod
    async def update_title(link_id: Optional[int], old_title: Optional[str], new_title: str):
        print(f"--- [DB] Renaming links to: '{new_title}' ---")
        async with AsyncSessionLocal() as session:
            if link_id:
                stmt = select(DownloadLink).where(DownloadLink.id == link_id)
            elif old_title:
                stmt = select(DownloadLink).where(DownloadLink.title.ilike(old_title))
            else:
                print("ERROR: You must specify either --id or --title to find links to rename.")
                return

            result = await session.execute(stmt)
            links = result.scalars().all()
            
            if not links:
                print(f"ERROR: No links found matching your criteria.")
                return
            
            count = 0
            for link in links:
                link.title = new_title
                link.imdb_id = None # Clear metadata for re-tagging
                count += 1
            
            await session.commit()
            print(f"SUCCESS: {count} link(s) renamed to '{new_title}'. Metadata cleared.")

    @staticmethod
    async def reset_all():
        print(f"--- [DB] Wiping ALL library metadata ---")
        async with AsyncSessionLocal() as session:
            # 1. Clear imdb_id from all links
            from sqlalchemy import update
            await session.execute(update(DownloadLink).values(imdb_id=None))
            
            # 2. Clear the MediaMetadata table
            from sqlalchemy import delete
            await session.execute(delete(MediaMetadata))
            
            await session.commit()
            print("SUCCESS: All metadata cleared. Library is now fresh.")

    @staticmethod
    async def audit():
        print("--- [DB] Database Metadata Audit ---")
        async with AsyncSessionLocal() as session:
            # 1. Total unique releases (all links)
            # 1. Total unique releases (all links) - matching dashboard logic
            stmt_total = select(func.count()).select_from(
                select(DownloadLink.id).group_by(
                    func.coalesce(DownloadLink.imdb_id, func.lower(DownloadLink.title)),
                    func.coalesce(DownloadLink.imdb_id, DownloadLink.year),
                    DownloadLink.category
                ).subquery()
            )
            total = (await session.execute(stmt_total)).scalar() or 0
            
            # 2. Untagged releases (no imdb_id)
            # 2. Untagged releases (no imdb_id)
            stmt_untagged = select(func.count()).select_from(
                select(DownloadLink.id).where(DownloadLink.imdb_id == None).group_by(
                    func.lower(DownloadLink.title), 
                    DownloadLink.year, 
                    DownloadLink.category
                ).subquery()
            )
            untagged = (await session.execute(stmt_untagged)).scalar() or 0
            
            # 3. Missing Title FR
            stmt_no_title_fr = select(func.count(MediaMetadata.imdb_id)).where(
                or_(MediaMetadata.title_fr == None, MediaMetadata.title_fr == "")
            )
            no_title_fr = (await session.execute(stmt_no_title_fr)).scalar() or 0

            # 4. Missing Plot FR
            stmt_no_plot = select(func.count(MediaMetadata.imdb_id)).where(
                or_(MediaMetadata.plot_fr == None, MediaMetadata.plot_fr == "")
            )
            no_plot = (await session.execute(stmt_no_plot)).scalar() or 0
            
            # 4. Missing Poster
            stmt_no_poster = select(func.count(MediaMetadata.imdb_id)).where(
                or_(MediaMetadata.poster_path == None, MediaMetadata.poster_path == "")
            )
            no_poster = (await session.execute(stmt_no_poster)).scalar() or 0
            
            # ANSI Colors
            CLR_C = "\033[96m" # Cyan
            CLR_Y = "\033[93m" # Yellow
            CLR_R = "\033[91m" # Red
            CLR_RESET = "\033[0m"

            print(f"Total Unique Releases: {CLR_C}{total}{CLR_RESET}")
            u_clr = CLR_Y if untagged > 0 else CLR_RESET
            print(f"Untagged (Missing ID): {u_clr}{untagged}{CLR_RESET} ({round(untagged/total*100, 1) if total > 0 else 0}%)")
            t_clr = CLR_Y if no_title_fr > 0 else CLR_RESET
            print(f"Missing Title (FR)   : {t_clr}{no_title_fr}{CLR_RESET}")
            p_clr = CLR_R if no_plot > 0 else CLR_RESET
            print(f"Missing Plot (FR)    : {p_clr}{no_plot}{CLR_RESET}")
            i_clr = CLR_R if no_poster > 0 else CLR_RESET
            print(f"Missing Posters      : {i_clr}{no_poster}{CLR_RESET}")
            
            # 5. List top 10 untagged (not just count)
            if untagged > 0:
                print(f"\n{CLR_C}Top 10 Untagged Releases (Recent):{CLR_RESET}")
                print("-" * 40)
                stmt_list = select(
                    DownloadLink.title, DownloadLink.year, DownloadLink.category, func.max(DownloadLink.last_checked)
                ).where(DownloadLink.imdb_id == None).group_by(
                    func.lower(DownloadLink.title), DownloadLink.year, DownloadLink.category
                ).order_by(func.max(DownloadLink.last_checked).desc()).limit(10)
                
                recent_untagged = (await session.execute(stmt_list)).all()
                for title, year, cat, last in recent_untagged:
                    y_str = f"({year})" if year else "(Auto)"
                    c_str = cat.upper() if cat else "N/A"
                    print(f"  - [{c_str}] {title} {y_str}")

class TagCommands:
    @staticmethod
    async def process(title: str = None, rename_to: str = None, year: int = None, media_type: str = None, limit: int = 500, repair: bool = False, imdb_id: str = None):
        async with AsyncSessionLocal() as session:
            if repair:
                await Categorizer.repair_metadata(session)
                await Categorizer.repair_links_metadata(session)
                return

            if title:
                print(f"--- [TAG] Manual tagging for: '{title}' (Year: {year or 'Auto'}, Type: {media_type or 'Auto'}) ---")
            else:
                print(f"--- [TAG] Batch tagging (Limit: {limit}) ---")

            if title:
                # Manual mode: find links by current title
                stmt = select(DownloadLink).where(DownloadLink.title == title)
                result = await session.execute(stmt)
                links = result.scalars().all()
                
                if not links:
                    print(f"[TAG] No exact title match for '{title}'. Trying restricted filename search...")
                    stmt = select(DownloadLink).where(
                        or_(
                            DownloadLink.filename.like(f"{title}.%"),
                            DownloadLink.filename.like(f"{title} %"),
                            DownloadLink.filename.like(f"{title}-%"),
                            DownloadLink.filename == title
                        )
                    )
                    result = await session.execute(stmt)
                    links = result.scalars().all()
                
                if not links:
                    print(f"[TAG] No links found for '{title}'.")
                    return
                
                # OPTIONAL: Rename to new title before tagging
                tag_title = title
                if rename_to:
                    print(f"[TAG] Renaming {len(links)} links from '{title}' to '{rename_to}'...")
                    for link in links:
                        link.title = rename_to
                    tag_title = rename_to

                # Clear old metadata to force re-tagging
                for link in links:
                    link.imdb_id = None
                    if year is not None:
                        link.year = year
                    if media_type is not None:
                        link.category = media_type
                        
                await Categorizer.enrich_links(session, links, force_year=year, force_type=media_type, force_imdb_id=imdb_id)
                await session.commit()
                
                # Fetch for display
                display_meta = None
                if links[0].imdb_id:
                    m_stmt = select(MediaMetadata).where(MediaMetadata.imdb_id == links[0].imdb_id)
                    m_res = await session.execute(m_stmt)
                    display_meta = m_res.scalar()

                print(f"[TAG] Successfully tagged {len(links)} links.")
                if display_meta:
                    print(f"\n--- METADATA FOUND ({display_meta.imdb_id}) ---")
                    print(f"Official Title: {display_meta.official_title}")
                    if display_meta.title_fr:
                        print(f"French Title: {display_meta.title_fr}")
                    print(f"Year: {display_meta.year}")
                    print(f"Poster: {display_meta.poster_path or 'None'}")
                    print(f"Plot (FR): {display_meta.plot_fr[:150] if display_meta.plot_fr else 'None'}...")
                    print("-" * 30)
                else:
                    print("\n[WARNING] No external metadata found for this title.")
            else:
                # Batch mode
                stmt = select(
                    DownloadLink.title, DownloadLink.year, DownloadLink.category
                ).where(DownloadLink.imdb_id == None).group_by(
                    DownloadLink.title, DownloadLink.year, DownloadLink.category
                ).limit(limit)
                
                result = await session.execute(stmt)
                triplets = result.all()
                
                if not triplets:
                    print("[TAG] Everything is already tagged!")
                    return

                for t_title, t_year, t_category in triplets:
                    if not t_title: continue
                    print(f"[TAG] Batch Processing: '{t_title}'")
                    
                    link_stmt = select(DownloadLink).where(
                        DownloadLink.title == t_title,
                        DownloadLink.year == t_year,
                        DownloadLink.category == t_category,
                        DownloadLink.imdb_id == None
                    )
                    links_result = await session.execute(link_stmt)
                    links = links_result.scalars().all()
                    
                    if links:
                        await Categorizer.enrich_links(session, links)
                        await session.commit()

class LinkCommands:
    @staticmethod
    async def reverify():
        print("--- [LINKS] Starting re-verification of dead links ---")
        hoster = Hoster()
        categorizer = Categorizer()
        
        async with AsyncSessionLocal() as session:
            stmt = select(DownloadLink).where(DownloadLink.status == "dead")
            result = await session.execute(stmt)
            dead_links = result.scalars().all()
            
            if not dead_links:
                print("[LINKS] No dead links found.")
                return

            print(f"[LINKS] Found {len(dead_links)} dead links to check.")
            
            batch_size = 50
            for i in range(0, len(dead_links), batch_size):
                batch = dead_links[i:i + batch_size]
                urls = [link.url for link in batch]
                
                results = await hoster.check_links(urls)
                recovered_count = 0
                for link_obj in batch:
                    info = results.get(link_obj.url)
                    if info and info.get("status") == "alive":
                        link_obj.status = "alive"
                        link_obj.filename = info.get("filename")
                        link_obj.hoster = info.get("host", "unknown")
                        link_obj.size_bytes = info.get("size", 0)
                        link_obj.size = format_size(link_obj.size_bytes)
                        link_obj.last_checked = datetime.now(timezone.utc)
                        
                        await categorizer.enrich_links(session, links=[link_obj])
                        recovered_count += 1
                
                await session.commit()
                print(f"[LINKS] Batch finished. {recovered_count} links recovered.")

    @staticmethod
    async def view(query: str):
        # ANSI Colors
        CLR_T = "\033[96m" # Cyan
        CLR_G = "\033[92m" # Green
        CLR_R = "\033[91m" # Red
        CLR_RESET = "\033[0m"

        print(f"--- [LINKS] Search results for: '{query}' ---")
        async with AsyncSessionLocal() as session:
            # 1. Search for links and potential metadata
            stmt = select(DownloadLink).where(
                (DownloadLink.title.ilike(f"%{query}%")) | 
                (DownloadLink.filename.ilike(f"%{query}%"))
            )
            
            # Also search if the query is an IMDB ID or matches an official title
            stmt_m = select(MediaMetadata).where(
                (MediaMetadata.official_title.ilike(f"%{query}%")) |
                (MediaMetadata.imdb_id == query)
            ).limit(1)
            m_res = await session.execute(stmt_m)
            m_meta = m_res.scalar()
            
            if m_meta:
                # Expand search to include all links with this IMDb ID
                stmt = select(DownloadLink).where(
                    or_(
                        DownloadLink.title.ilike(f"%{query}%"),
                        DownloadLink.filename.ilike(f"%{query}%"),
                        DownloadLink.imdb_id == m_meta.imdb_id
                    )
                )
                
            result = await session.execute(stmt)
            links = result.scalars().all()
            
            if not links:
                print(f"No match found for '{query}'.")
                return

            # 2. Group links by their metadata (imdb_id or title/year)
            groups = {} # group_key -> list of links
            for link in links:
                key = link.imdb_id if link.imdb_id else f"{link.title}-{link.year}"
                if key not in groups: groups[key] = []
                groups[key].append(link)

            print(f"Found {len(links)} records in {len(groups)} groups.\n")

            # 3. Display each group
            for key, group_links in groups.items():
                # Get metadata for the group header
                meta = None
                if group_links[0].imdb_id:
                    m_stmt = select(MediaMetadata).where(MediaMetadata.imdb_id == group_links[0].imdb_id)
                    m_res = await session.execute(m_stmt)
                    meta = m_res.scalar()
                
                title = meta.official_title if meta else group_links[0].title
                year = meta.year if meta else group_links[0].year
                i_id = meta.imdb_id if meta else "No ID"
                
                print(f"{CLR_T}=== {title} ({year}) [{i_id}] ==={CLR_RESET}")
                if meta and meta.plot_fr:
                    print(f"Plot: {meta.plot_fr[:160]}...")
                
                # Header for the links table
                print(f"{'ID':<6} | {'Qual/Res':<15} | {'Lang':<6} | {'Size':<9} | {'Hoster':<12} | {'Status'}")
                print("-" * 80)
                
                for link in group_links:
                    status_clr = CLR_G if link.status == "alive" else CLR_R
                    status_txt = f"{status_clr}{link.status.upper()}{CLR_RESET}"
                    
                    q_r = f"{link.quality or '?'}/{link.resolution or '?'}"
                    print(f"{link.id:<6} | {q_r:<15} | {link.language or '?' :<6} | {link.size or '?' :<9} | {link.hoster or '?' :<12} | {status_txt}")
                    # Sub-line for filename/URL (optional: only if query is not exact filename)
                    print(f"  > {link.filename}")
                    print(f"  > {link.url}")
                
                print("\n")
                
class ScanCommands:
    @staticmethod
    async def trigger():
        from app.core.scheduler import run_scrapers
        print("--- [SCAN] Starting manual full scan ---")
        try:
            await run_scrapers()
            print("--- [SCAN] Manual scan finished ---")
        except Exception as e:
            print(f"[SCAN] Error during manual scan: {e}")
