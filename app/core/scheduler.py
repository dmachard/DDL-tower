import asyncio
import random
import traceback
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DownloadLink
from app.core.scraper import Scraper
from app.core.link import LinkManager
from app.services.enrichment_service import enrichment_service
from app.core.config import settings
from app.db.database import get_db_ctx

async def get_scrapers():
    """Initialize scrapers based on settings."""
    scrapers = []
    for config in settings.SCRAPER_SOURCES:
        scrapers.append(Scraper(config))
    return scrapers

async def run_scraper(scraper):
    """Run a single scraper and process found links."""
    print(f"[SCHEDULER] Running scraper: {scraper.name}")
    try:
        manager = LinkManager()
        async for batch in scraper.run():
            links = batch.get("links", [])
            source_url = batch.get("source_url")
            override_title = batch.get("override_title")
            override_year = batch.get("override_year")
            tags = batch.get("tags", [])
            category = batch.get("category")

            if links:
                # 1. Insert/Update links first (Short transaction)
                added = []
                async with get_db_ctx() as db:
                    added = await manager.check_links(
                        db, 
                        links, 
                        source_url=source_url, 
                        source_name=scraper.name, 
                        override_title=override_title, 
                        override_year=int(override_year) if override_year and str(override_year).isdigit() else None,
                        tags=tags,
                        category=category
                    )
                
                # 2. Enrich links (Separate transaction, can take time)
                if added:
                    async with get_db_ctx() as db:
                        # Re-fetch objects in new session or use IDs? 
                        # Categorizer.enrich_links can take a list of objects, 
                        # but they must be attached to the current session.
                        # We'll pass the IDs to be safe or just re-run for missing titles.
                        link_ids = [l.id for l in added if l.id]
                        if link_ids:
                            from sqlalchemy import select
                            stmt = select(DownloadLink).where(DownloadLink.id.in_(link_ids))
                            res = await db.execute(stmt)
                            links_to_enrich = res.scalars().all()
                            
                            url_to_poster = {}
                            poster_url = batch.get("poster_url")
                            if poster_url:
                                for l in links_to_enrich:
                                    url_to_poster[l.url] = poster_url
                            
                            await enrichment_service.enrich_links(db, links=links_to_enrich, url_to_poster=url_to_poster)
                        
                        # 3. Auto-download if requested in scraper config
                        auto_download = batch.get("auto_download")
                        if auto_download:
                            # Determine if there is any year restriction
                            allowed_years = []
                            if isinstance(auto_download, list):
                                allowed_years = auto_download
                            elif isinstance(batch.get("auto_download_years"), list):
                                allowed_years = batch.get("auto_download_years")
                            
                            should_download = True
                            if allowed_years:
                                # Find parsed/enriched year from the links in this batch
                                year_found = None
                                for link in (links_to_enrich or []):
                                    if link.year:
                                        year_found = link.year
                                        break
                                
                                if year_found:
                                    # Type-safe check for matching year
                                    def matches_allowed_years(y, allowed):
                                        try:
                                            y_int = int(y)
                                        except (ValueError, TypeError):
                                            return False
                                        for ay in allowed:
                                            try:
                                                if int(ay) == y_int:
                                                    return True
                                            except (ValueError, TypeError):
                                                if str(ay).strip() == str(y).strip():
                                                    return True
                                        return False
                                    
                                    if not matches_allowed_years(year_found, allowed_years):
                                        print(f"[SCHEDULER] [{scraper.name}] ⏭ Auto-download skipped: Year {year_found} not in allowed years {allowed_years}")
                                        should_download = False
                                else:
                                    print(f"[SCHEDULER] [{scraper.name}] ⏭ Auto-download skipped: No year found for release and year filters {allowed_years} are active")
                                    should_download = False
                            
                            allowed_keywords = batch.get("auto_download_keywords", [])
                            if isinstance(allowed_keywords, str):
                                allowed_keywords = [allowed_keywords]
                            
                            if should_download and allowed_keywords:
                                keyword_found = False
                                for link in (links_to_enrich or []):
                                    link_text = f"{link.title or ''} {link.filename or ''}".lower()
                                    for kw in allowed_keywords:
                                        if str(kw).lower() in link_text:
                                            keyword_found = True
                                            break
                                    if keyword_found:
                                        break
                                
                                if not keyword_found:
                                    print(f"[SCHEDULER] [{scraper.name}] ⏭ Auto-download skipped: No keyword from {allowed_keywords} found in release")
                                    should_download = False
                            
                            if should_download:
                                from app.api.downloads import run_download_task
                                # We run it in the background as a task to not block the scraper
                                asyncio.create_task(run_download_task(links, is_auto=True))
    except Exception as e:
        print(f"[SCHEDULER] Error running scraper {scraper.name}: {e}")
        traceback.print_exc()

async def run_scrapers(source_name: str = None):
    """Runs all scrapers or a specific one once. Used by manual trigger."""
    scrapers = await get_scrapers()
    for scraper in scrapers:
        if source_name:
            if scraper.name.lower() != source_name.lower():
                continue
        elif not scraper.enabled:
            print(f"[SCHEDULER] Skipping scraper {scraper.name} (disabled in config)")
            continue
        
        await run_scraper(scraper)
    
    # Categorization (Enrichment)
    async with get_db_ctx() as db:
        await enrichment_service.enrich_links(db)
        # commit is handled by get_db_ctx

async def run_categorization():
    """Runs the categorization process only."""
    async with get_db_ctx() as db:
        await enrichment_service.enrich_links(db)

def is_in_scan_window():
    from datetime import datetime
    now = datetime.now()
    start = settings.SCAN_START_HOUR
    end = settings.SCAN_END_HOUR
    
    # If both are same, assume 24h scanning
    if start == end:
        return True
        
    current_hour = now.hour
    
    if start < end:
        return start <= current_hour < end
    else:
        # Crosses midnight (e.g. 6 to 0)
        return current_hour >= start or current_hour < end

async def scheduler_loop():
    """Main scheduler loop."""
    print(f"[SCHEDULER] Starting with interval: {settings.SCAN_INTERVAL_MINUTES} minutes")
    print(f"[SCHEDULER] Allowed window: {settings.SCAN_START_HOUR:02d}h to {settings.SCAN_END_HOUR:02d}h")
    
    while True:
        try:
            if not is_in_scan_window():
                print(f"[SCHEDULER] [{datetime_now()}] Outside allowed window. Sleeping 10 minutes...")
                await asyncio.sleep(600)
                continue

            print(f"[SCHEDULER] [{datetime_now()}] Starting sequence...")
            await run_scrapers()
            
            # Randomize interval (jitter +/- 20%)
            base_interval = settings.SCAN_INTERVAL_MINUTES
            jitter = random.uniform(0.8, 1.2)
            wait_minutes = base_interval * jitter
            
            print(f"[SCHEDULER] Sequence finished. Waiting {wait_minutes:.1f} minutes (randomized from {base_interval}m).")
            await asyncio.sleep(wait_minutes * 60)
            
        except Exception as e:
            print(f"[SCHEDULER] Critical error: {e}")
            traceback.print_exc()
            await asyncio.sleep(60)

def datetime_now():
    from datetime import datetime
    return datetime.now().strftime("%H:%M:%S")

def start_scheduler():
    """Starts the scheduler in the background."""
    asyncio.create_task(scheduler_loop())
