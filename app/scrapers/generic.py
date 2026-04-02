import re
import asyncio
from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from playwright.async_api import async_playwright
from app.scrapers.base import BaseScraper
from app.db.models import ScrapedURL

class GenericScraper(BaseScraper):
    def __init__(self, config: dict):
        self._name = config.get("name", "Generic")
        self.entry_url = config.get("entry_url")
        self.entry_wait_for = config.get("entry_wait_for")
        self.crawls = config.get("crawls", [])
        self.target_patterns = config.get("target_patterns", [])

    @property
    def name(self) -> str:
        return self._name

    async def run(self, session: Optional[AsyncSession] = None) -> AsyncGenerator[List[str], None]:
        async with async_playwright() as p:
            # On utilise pas d'headless pour debugger si besoin ou selon config
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            try:
                # 1. Load entry URL
                print(f"[{self.name}] Load entry URL: {self.entry_url}")
                await page.goto(self.entry_url, wait_until="networkidle", timeout=30000)
                
                # Get page content
                html = await page.content()
                
                # Check for entry wait condition (and capture status)
                entry_status = "success"
                if self.entry_wait_for:
                    try:
                        await page.wait_for_selector(self.entry_wait_for, timeout=5000)
                        # Refresh html after wait to get dynamic content
                        html = await page.content()
                    except:
                        entry_status = "failed"
                        print(f"[{self.name}] ERROR: entry wait condition not found: {self.entry_wait_for}")
                
                # Record visit of the entry URL in database (with final status)
                if session:
                    scraped_entry = ScrapedURL(
                        url=self.entry_url, 
                        source_name=self.name, 
                        status=entry_status,
                        scrape_once=False,
                        last_scraped=datetime.now(timezone.utc)
                    )
                    await session.merge(scraped_entry)
                    await session.commit()

                if entry_status == "failed":
                    return # Stop here for this scraper

                # 2. Execute crawling steps (if present)
                if self.crawls:
                    for crawl in self.crawls:
                        pattern = crawl.get("pattern")
                        wait_condition = crawl.get("wait_for")

                        if not pattern:
                            continue
                            
                        sublinks = list(dict.fromkeys(re.findall(pattern, html)))
                        
                        scrape_once = crawl.get("scrape_once", False)

                        # Logic to skip if already scraped and scrape_once is true (FILTER BEFORE LOOP)
                        if scrape_once and session:
                            # Efficiency: query all at once
                            stmt = select(ScrapedURL.url).where(ScrapedURL.url.in_(sublinks))
                            result = await session.execute(stmt)
                            already_scraped = set(r[0] for r in result.all())
                            
                            original_count = len(sublinks)
                            sublinks = [s for s in sublinks if s not in already_scraped]
                            skipped = original_count - len(sublinks)
                            
                            if skipped > 0:
                                print(f"[{self.name}] Found {original_count} sublinks, skipped {skipped} already processed.")
                                
                        print(f"[{self.name}] Processing {len(sublinks)} sublinks from pattern '{pattern}'...")

                        for idx, url in enumerate(sublinks, 1):
                            try:
                                print(f"[{self.name}] Load sublink {idx}/{len(sublinks)}: {url}")
                                await page.goto(url, wait_until="networkidle", timeout=30000)
                                
                                wait_condition_failed = False
                                # Optional wait specific to this crawl step
                                if wait_condition:
                                    try:
                                        await page.wait_for_selector(wait_condition, timeout=4000)
                                    except:
                                        print(f"[{self.name}] crawl failed: wait condition not found for '{wait_condition}' on {url}")
                                        wait_condition_failed = True

                                # Record visit in database (Always tracked now)
                                if session:
                                    scraped_entry = ScrapedURL(
                                        url=url, 
                                        source_name=self.name, 
                                        status="success" if not wait_condition_failed else "failed",
                                        scrape_once=scrape_once,
                                        last_scraped=datetime.now(timezone.utc)
                                    )
                                    await session.merge(scraped_entry)
                                    await session.commit()

                                if wait_condition_failed:
                                    continue
                                
                                inner_html = await page.content()
                                
                                # Extract target links from subpage
                                found_in_subpage = []
                                for t_pattern in self.target_patterns:
                                    found = re.findall(t_pattern, inner_html)
                                    found_in_subpage.extend(found)
                                
                                if found_in_subpage:
                                    print(f"[{self.name}] Found {len(found_in_subpage)} target links on {url}")
                                    yield list(dict.fromkeys(found_in_subpage))
                                else:
                                    print(f"[{self.name}] No target links found on {url}")
                                
                            except Exception as e:
                                print(f"[{self.name}] Error on sublink {url}: {e}")
                else:
                    # If no sub-steps, search directly on entry page
                    found_links = []
                    for pattern in self.target_patterns:
                        found = re.findall(pattern, html)
                        found_links.extend(found)
                    if found_links:
                        yield list(dict.fromkeys(found_links))

            except Exception as e:
                print(f"[{self.name}] ERROR: {e}")
            finally:
                await browser.close()
