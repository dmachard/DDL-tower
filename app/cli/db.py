import asyncio
from typing import Optional
from app.services.maintenance_service import maintenance_service
from app.db.database import AsyncSessionLocal
from app.db.models import DownloadLink, MediaMetadata
from sqlalchemy import select, update, delete

class DBCommands:
    @staticmethod
    async def backup(output_path: str = "data/backup.json"):
        print(f"--- [DB] Exporting database to {output_path} ---")
        l_count, s_count = await maintenance_service.backup_db(output_path)
        print(f"SUCCESS: Exported {l_count} links and {s_count} history entries.")

    @staticmethod
    async def restore(input_path: str = "data/backup.json"):
        print(f"--- [DB] Restoring database from {input_path} ---")
        l_count, s_count = await maintenance_service.restore_db(input_path)
        if l_count is None:
            print(f"ERROR: Backup file {input_path} not found.")
        else:
            print(f"SUCCESS: Restored {l_count} links and {s_count} history entries.")

    @staticmethod
    async def reset_scans(pattern: str = None):
        from app.db.models import ScrapedURL
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
            stmt = update(DownloadLink).values(imdb_id=None).where(DownloadLink.imdb_id != None)
            if title: stmt = stmt.where(DownloadLink.title.ilike(f"%{title}%"))
            if imdb_id: stmt = stmt.where(DownloadLink.imdb_id == imdb_id)
            result = await session.execute(stmt)
            affected = result.rowcount
            
            if title:
                await session.execute(delete(MediaMetadata).where(MediaMetadata.official_title.ilike(f"%{title}%")))
            if imdb_id:
                await session.execute(delete(MediaMetadata).where(MediaMetadata.imdb_id == imdb_id))

            await session.commit()
            print(f"SUCCESS: Reset {affected} links. Central metadata cleaned.")
            
    @staticmethod
    async def cleanup():
        print("--- [DB] Global Title Harmonization ---")
        unique_groups, updated_fields = await maintenance_service.harmonize_titles()
        print(f"[DB] Found {unique_groups} unique title groups. Harmonizing...")
        print(f"\nSUCCESS: Harmonized {updated_fields} link fields (titles/years).")

    @staticmethod
    async def update_title(link_id: Optional[int], old_title: Optional[str], new_title: str):
        print(f"--- [DB] Renaming links to: '{new_title}' ---")
        async with AsyncSessionLocal() as session:
            if link_id:
                stmt = select(DownloadLink).where(DownloadLink.id == link_id)
            elif old_title:
                stmt = select(DownloadLink).where(DownloadLink.title.ilike(old_title))
            else:
                print("ERROR: You must specify either --id or --title.")
                return

            result = await session.execute(stmt)
            links = result.scalars().all()
            if not links:
                print(f"ERROR: No links found matching your criteria.")
                return
            
            for link in links:
                link.title = new_title
                link.imdb_id = None
            await session.commit()
            print(f"SUCCESS: {len(links)} link(s) renamed to '{new_title}'. Metadata cleared.")

    @staticmethod
    async def reset_all():
        print(f"--- [DB] Wiping ALL library metadata ---")
        async with AsyncSessionLocal() as session:
            await session.execute(update(DownloadLink).values(imdb_id=None))
            await session.execute(delete(MediaMetadata))
            await session.commit()
            print("SUCCESS: All metadata cleared. Library is now fresh.")

    @staticmethod
    async def wipe():
        from app.db.models import ScrapedURL
        print(f"--- [DB] WIPING ENTIRE DATABASE (Links, Metadata, History) ---")
        async with AsyncSessionLocal() as session:
            await session.execute(delete(DownloadLink))
            await session.execute(delete(MediaMetadata))
            await session.execute(delete(ScrapedURL))
            await session.commit()
            print("SUCCESS: Database is now completely empty.")

    @staticmethod
    async def audit():
        print("--- [DB] Database Metadata Audit ---")
        res = await maintenance_service.audit_metadata()
        
        CLR_C = "\033[96m" # Cyan
        CLR_Y = "\033[93m" # Yellow
        CLR_R = "\033[91m" # Red
        CLR_RESET = "\033[0m"

        print(f"Total Unique Releases: {CLR_C}{res['total']}{CLR_RESET}")
        u_clr = CLR_Y if res['untagged'] > 0 else CLR_RESET
        print(f"Untagged (Missing ID): {u_clr}{res['untagged']}{CLR_RESET} ({round(res['untagged']/res['total']*100, 1) if res['total'] > 0 else 0}%)")
        print(f"Missing Title (FR)   : {CLR_Y if res['no_title_fr'] > 0 else CLR_RESET}{res['no_title_fr']}{CLR_RESET}")
        print(f"Missing Plot (FR)    : {CLR_R if res['no_plot'] > 0 else CLR_RESET}{res['no_plot']}{CLR_RESET}")
        print(f"Missing Posters      : {CLR_R if res['no_poster'] > 0 else CLR_RESET}{res['no_poster']}{CLR_RESET}")
        
        if res['untagged'] > 0:
            print(f"\n{CLR_C}Top 10 Untagged Releases (Recent):{CLR_RESET}")
            print("-" * 40)
            for title, year, cat, last in res['recent_untagged']:
                y_str = f"({year})" if year else "(Auto)"
                c_str = cat.upper() if cat else "N/A"
                print(f"  - [{c_str}] {title} {y_str}")
