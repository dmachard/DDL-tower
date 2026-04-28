import asyncio
import traceback
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scraper import Scraper
from app.core.link import LinkManager
from app.core.categorization import Categorizer
from app.core.config import settings
from app.db.database import get_db

async def get_scrapers():
    """Initialize scrapers based on settings."""
    scrapers = []
    for config in settings.SCRAPER_SOURCES:
        scrapers.append(Scraper(config))
    return scrapers

async def run_scraper(scraper, db: AsyncSession):
    """Run a single scraper and process found links."""
    print(f"[SCHEDULER] Running scraper: {scraper.name}")
    try:
        manager = LinkManager()
        async for batch in scraper.run(session=db):
            links = batch.get("links", [])
            source_url = batch.get("source_url")
            override_title = batch.get("override_title")
            override_year = batch.get("override_year")
            tags = batch.get("tags", [])

            if links:
                # Use check_links which handles verification and DB insertion
                added = await manager.check_links(
                    db, 
                    links, 
                    source_url=source_url, 
                    source_name=scraper.name, 
                    override_title=override_title, 
                    override_year=int(override_year) if override_year and str(override_year).isdigit() else None,
                    tags=tags
                )
                if added:
                    # Enrich and commit this batch immediately
                    await Categorizer.enrich_links(db, links=added)
                    await db.commit()
    except Exception as e:
        print(f"[SCHEDULER] Error running scraper {scraper.name}: {e}")
        traceback.print_exc()

async def run_scrapers(source_name: str = None):
    """Runs all scrapers or a specific one once. Used by manual trigger."""
    async for db in get_db():
        scrapers = await get_scrapers()
        for scraper in scrapers:
            if source_name and scraper.name.lower() != source_name.lower():
                continue
            await run_scraper(scraper, db)
        
        # Categorization (Enrichment)
        await Categorizer.enrich_links(db)
        await db.commit()

async def run_categorization():
    """Runs the categorization process only."""
    async for db in get_db():
        await Categorizer.enrich_links(db)
        await db.commit()

async def scheduler_loop():
    """Main scheduler loop."""
    print(f"[SCHEDULER] Starting with interval: {settings.SCAN_INTERVAL_MINUTES} minutes")
    
    while True:
        try:
            print(f"[SCHEDULER] [{datetime_now()}] Starting sequence...")
            await run_scrapers()
            print(f"[SCHEDULER] Sequence finished. Waiting {settings.SCAN_INTERVAL_MINUTES} minutes.")
            await asyncio.sleep(settings.SCAN_INTERVAL_MINUTES * 60)
            
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
