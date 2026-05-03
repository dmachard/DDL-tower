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
from app.services.enrichment_service import enrichment_service

class DirectScanner:
    def __init__(self):
        self.link_manager = LinkManager()
        # Use explicit patterns from config
        self.target_patterns = settings.DIRECT_SCAN_PATTERNS

    async def scan_urls(self, urls: List[str]):
        """
        Processes a list of URLs and returns stats.
        """
        results = []
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
                    await page.goto(url, wait_until="networkidle", timeout=60000)
                    
                    # Extract from all frames
                    all_content = [await page.content()]
                    for frame in page.frames:
                        try:
                            all_content.append(await frame.content())
                        except:
                            continue
                    
                    combined_content = " ".join(all_content)
                    
                    found_links = set()
                    for pattern in self.target_patterns:
                        found_links.update(re.findall(pattern, combined_content))
                    
                    total_found = len(found_links)
                    
                    async with AsyncSessionLocal() as session:
                        if not found_links:
                            scraped_entry = ScrapedURL(
                                url=url,
                                source_name="Direct-Scan",
                                status="finished",
                                scrape_once=True,
                                last_scraped=datetime.now(timezone.utc),
                                duration_ms=int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
                            )
                            await session.merge(scraped_entry)
                            await session.commit()
                            results.append({"url": url, "total": 0, "new": 0})
                            continue
                        
                        print(f"[DIRECT-SCAN] Found {total_found} links on {url}")
                        new_links = await self.link_manager.check_links(
                            session=session,
                            raw_links=list(found_links),
                            source_url=url,
                            source_name="Direct-Scan"
                        )
                        new_added = len(new_links) if new_links else 0
                        await session.commit()
                        
                        if new_links:
                            await enrichment_service.enrich_links(session, links=new_links)
                            await session.commit()
                        
                        results.append({"url": url, "total": total_found, "new": new_added})
                        
                except Exception as e:
                    print(f"[DIRECT-SCAN] Error scanning {url}: {e}")
                    results.append({"url": url, "error": str(e)})
                finally:
                    await page.close()
            
            await browser.close()
        return results

    async def scan_text(self, text: str):
        """
        Extracts links from raw text using configured patterns and processes them.
        """
        found_links = set()
        for pattern in self.target_patterns:
            found_links.update(re.findall(pattern, text))
        
        if not found_links:
            print("[DIRECT-SCAN] No links found in provided text.")
            return []

        total_found = len(found_links)
        print(f"[DIRECT-SCAN] Found {total_found} links in text.")
        
        async with AsyncSessionLocal() as session:
            new_links = await self.link_manager.check_links(
                session=session,
                raw_links=list(found_links),
                source_url="manual-paste",
                source_name="Quick-Scan"
            )
            await session.commit()
            
            new_added = len(new_links) if new_links else 0
            
            if new_links:
                await enrichment_service.enrich_links(session, links=new_links)
                await session.commit()
            
            return {
                "total_found": total_found,
                "new_added": new_added,
                "links": new_links
            }
