from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.scrapers.crawl_scraper import CrawlScraper
from app.scrapers.rss_scraper import RSSScraper
from app.scrapers.webtop_scraper import WebtopScraper
from app.core.link import LinkManager
from app.core.categorization import Categorizer

scheduler = AsyncIOScheduler()

async def run_scrapers():
    print(f"[SCHEDULER] [{datetime.now().strftime('%H:%M:%S')}] Starting sequence...")
    
    scrapers = []
    for config in settings.SCRAPER_SOURCES:
        if "rss_url" in config:
            scrapers.append(RSSScraper(config))
        elif "js_items" in config or config.get("use_webtop"):
            scrapers.append(WebtopScraper(config))
        else:
            scrapers.append(CrawlScraper(config))

    link_manager = LinkManager()
    categorizer = Categorizer()
    
    async with AsyncSessionLocal() as session:
        # STEP A: DISCOVERY & LINK STORAGE (Per scraper)
        for scraper in scrapers:
            try:
                print(f"[SCHEDULER] Running scraper: {scraper.name}")
                # Iterate over the async generator to process links in real-time
                async for batch in scraper.run(session):
                    if not batch:
                        continue
                    
                    # Scrapers now return a dictionary with links and optional metadata
                    if isinstance(batch, dict):
                        links = batch.get("links")
                        override_filename = batch.get("override_filename")
                        batch_source_url = batch.get("source_url")
                        batch_tags = batch.get("tags")
                    else:
                        links = batch
                        override_filename = None
                        batch_source_url = None
                        batch_tags = None
                    
                    if not links:
                        continue

                    # Determine source URL for tracking: prioritize the precise URL from the batch
                    s_url = batch_source_url or getattr(scraper, "entry_url", None) or getattr(scraper, "rss_url", None)

                    # check the status of links
                    new_links = await link_manager.check_links(
                        session=session,
                        raw_links=links,
                        source_url=s_url,
                        source_name=scraper.name,
                        override_filename=override_filename,
                        tags=batch_tags
                    )
                    
                    # Commit immediately for UI display
                    await session.commit()
                    
                    if new_links:
                        print(f"[SCHEDULER] Batch of {len(new_links)} new links from '{scraper.name}' stored. Starting enrichment...")
                        # Immediate enrichment for badge display (WOW effect)
                        try:
                            await categorizer.enrich_links(session, links=new_links)
                            await session.commit()
                            print(f"[SCHEDULER] Real-time enrichment for '{scraper.name}' finished.")
                        except Exception as e:
                            print(f"[SCHEDULER] Real-time enrichment error for '{scraper.name}': {e}")
                    else:
                        print(f"[SCHEDULER] No new links from '{scraper.name}' in this batch.")
                
                print(f"[SCHEDULER] Full scan for '{scraper.name}' finished.")
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
