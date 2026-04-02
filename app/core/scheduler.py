from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.scrapers.generic import GenericScraper
from app.core.link import LinkManager
from app.core.categorization import Categorizer

scheduler = AsyncIOScheduler()

async def run_scrapers():
    """
    Sequential Orchestrator: 
    1. Discovery (Scraper) -> raw links
    2. Verification & Storage (LinkManager) -> Fill DownloadLink
    3. Enrichment (Categorizer) -> Metadata extraction (Title, Season, Resolution, Codec, Multi...)
    """
    print(f"[SCHEDULER] [{datetime.now().strftime('%H:%M:%S')}] Starting sequence...")
    
    scrapers = [GenericScraper(config) for config in settings.SCRAPER_SOURCES]
    link_manager = LinkManager()
    categorizer = Categorizer()
    
    async with AsyncSessionLocal() as session:
        # STEP A: DISCOVERY & LINK STORAGE (Per scraper)
        for scraper in scrapers:
            try:
                # Iterate over the async generator to process links in real-time
                async for links_batch in scraper.run(session):
                    if not links_batch:
                        continue

                    # The Link module handles its own table and AllDebrid
                    await link_manager.check_links(
                        session=session,
                        raw_links=links_batch,
                        source_url=scraper.entry_url,
                        source_name=scraper.name
                    )
                    
                    # Commit immediately for UI display
                    await session.commit()
                    print(f"[SCHEDULER] Batch of {len(links_batch)} links from '{scraper.name}' stored (real-time).")

                    # Immediate enrichment for badge display (WOW effect)
                    try:
                        await categorizer.enrich_links(session)
                        await session.commit()
                        print(f"[SCHEDULER] Real-time enrichment for '{scraper.name}' finished.")
                    except Exception as e:
                        print(f"[SCHEDULER] Real-time enrichment error: {e}")
                
                print(f"[SCHEDULER] Full scan for '{scraper.name}' finished.")

                # STEP B: ENRICHMENT (Immediate for the current scraper)
                try:
                    await run_categorization()
                    print(f"[SCHEDULER] Metadata enrichment for '{scraper.name}' finished.")
                except Exception as e:
                    print(f"[SCHEDULER] Error in enrichment phase for '{scraper.name}': {e}")

            except Exception as e:
                print(f"[SCHEDULER] Error in cycle for '{scraper.name}': {e}")
                await session.rollback()

async def run_categorization():
    """
    Runs only the metadata enrichment process for raw links.
    """
    print(f"[SCHEDULER] [{datetime.now().strftime('%H:%M:%S')}] Starting standalone enrichment...")
    categorizer = Categorizer()
    async with AsyncSessionLocal() as session:
        try:
            await categorizer.enrich_links(session)
            await session.commit()
            print("[SCHEDULER] Standalone enrichment finished.")
        except Exception as e:
            print(f"[SCHEDULER] Error in standalone enrichment: {e}")
            await session.rollback()
            raise e

def start_scheduler():
    scheduler.add_job(
        run_scrapers, 
        'interval', 
        minutes=settings.SCAN_INTERVAL_MINUTES, 
        id='periodic_scan_job',
        next_run_time=datetime.now()
    )
    scheduler.start()
    print(f"[SCHEDULER] Sequential scan scheduled every {settings.SCAN_INTERVAL_MINUTES} minutes.")
