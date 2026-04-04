import re
import asyncio
from datetime import datetime, timezone
from typing import List, Set
from playwright.async_api import async_playwright
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import ScrapedURL, DownloadLink
from app.core.link import LinkManager
from app.core.categorization import Categorizer

class DirectScanner:
    def __init__(self):
        self.link_manager = LinkManager()
        self.categorizer = Categorizer()
        # Use explicit patterns from config
        self.target_patterns = settings.DIRECT_SCAN_PATTERNS

    async def scan_urls(self, urls: List[str]):
        """
        Processes a list of URLs in the background.
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            # Use a realistic User-Agent to avoid basic bot blocks
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            context = await browser.new_context(user_agent=user_agent)
            
            for url in urls:
                if not url.strip():
                    continue
                
                print(f"[DIRECT-SCAN] Processing URL: {url}")
                page = await context.new_page()
                start_time = datetime.now(timezone.utc)
                try:
                    # 1. Visit the URL
                    await page.goto(url, wait_until="domcontentloaded", timeout=45000)

                    # 3. Wait for dynamic content
                    await asyncio.sleep(3) # Safe buffer for JS rendering
                    
                    # 4. Extract from ALL frames (Essential for ControlC/PrivateBin iframes)
                    all_html = []
                    for frame in page.frames:
                        try:
                            frame_html = await frame.content()
                            all_html.append(frame_html)
                        except Exception:
                            continue
                    
                    full_html = " ".join(all_html)
                    print("[DIRECT-SCAN] Page loaded. Size: ", len(full_html))
   
                    # 5. Extract target links only
                    found_links = set()
                    for pattern in self.target_patterns:
                        found_links.update(re.findall(pattern, full_html))
                    
                    duration = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

                    # 6. Store and process results
                    async with AsyncSessionLocal() as session:
                        # Record visit
                        scraped_entry = ScrapedURL(
                            url=url,
                            source_name="Direct-Scan",
                            status="success" if found_links else "no_links",
                            scrape_once=True,
                            last_scraped=datetime.now(timezone.utc),
                            duration_ms=duration
                        )
                        await session.merge(scraped_entry)
                        
                        if not found_links:
                            print(f"[DIRECT-SCAN] No links found on {url}")
                            await session.commit()
                            continue
                        
                        print(f"[DIRECT-SCAN] Found {len(found_links)} links on {url}")
                        # Use LinkManager to check mortality and store in DownloadLink
                        # It returns only the NEW links added to the database
                        new_links = await self.link_manager.check_links(
                            session=session,
                            raw_links=list(found_links),
                            source_url=url,
                            source_name="Direct-Scan"
                        )
                            
                        # Commit so Categorizer can see them
                        await session.commit()
                        
                        # Enrich metadata ONLY for the newly added links!
                        if new_links:
                            await self.categorizer.enrich_links(session, links=new_links)
                            await session.commit()
                        
                except Exception as e:
                    print(f"[DIRECT-SCAN] Error scanning {url}: {e}")
                    duration = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
                    async with AsyncSessionLocal() as session:
                        scraped_entry = ScrapedURL(
                            url=url,
                            source_name="Direct-Scan",
                            status="failed",
                            scrape_once=True,
                            last_scraped=datetime.now(timezone.utc),
                            duration_ms=duration
                        )
                        await session.merge(scraped_entry)
                        await session.commit()
                finally:
                    await page.close()
            
            await browser.close()
