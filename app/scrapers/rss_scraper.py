import re
import asyncio
import httpx
import feedparser
from typing import List, Optional, AsyncGenerator, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from playwright.async_api import async_playwright, Page
from app.scrapers.base import BaseScraper
from app.db.models import ScrapedURL

class RSSScraper(BaseScraper):
    """
    RSS Scraper
    """
    def __init__(self, config: dict):
        self._name = config.get("name", "RSS")
        self.rss_url = config.get("rss_url")
        self.required_keywords = config.get("required_keywords", [])
        self.click_selector = config.get("click_selector")
        self.target_patterns = config.get("target_patterns", [])

    @property
    def name(self) -> str:
        return self._name

    async def run(self, session: Optional[AsyncSession] = None) -> AsyncGenerator[Dict[str, Any], None]:
        async with async_playwright() as p:
            # We use headless mode for simplicity, but can be configured
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            # 1. Gather URLs to process from RSS
            items_to_process = []
            if self.rss_url:
                try:
                    print(f"[RSS_SCRAPER] [{self.name}] Fetching RSS: {self.rss_url}")
                    async with httpx.AsyncClient(follow_redirects=True) as client:
                        resp = await client.get(self.rss_url, timeout=30)
                        if resp.status_code == 200:
                            feed = feedparser.parse(resp.text)
                            for entry in feed.entries:
                                url = entry.get("link")
                                title = entry.get("title", "")
                                if url:
                                    items_to_process.append({"url": url, "title": title, "scrape_once": True})
                except Exception as e:
                    print(f"[RSS_SCRAPER] [{self.name}] RSS Error: {e}")
                else:
                    print(f"[RSS_SCRAPER] [{self.name}] Found {len(items_to_process)} items in RSS.")

            # 3. Process each item
            for item in items_to_process:
                url = item["url"]
                rss_title = item["title"]
                should_scrape_once = item["scrape_once"]

                # Skip if already processed for 'scrape_once' items
                if should_scrape_once and session:
                    stmt = select(ScrapedURL).where(ScrapedURL.url == url)
                    res = await session.execute(stmt)
                    if res.scalar():
                        # Already done, skip
                        continue

                try:
                    print(f"[RSS_SCRAPER] [{self.name}] Visiting: {url}")
                    start_time = datetime.now(timezone.utc)
                    await page.goto(url, wait_until="networkidle", timeout=45000)
                    
                    duration = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

                    # Record visit in DB
                    if session:
                        scraped_entry = ScrapedURL(
                            url=url, 
                            source_name=self.name, 
                            status="success",
                            scrape_once=should_scrape_once,
                            last_scraped=datetime.now(timezone.utc),
                            duration_ms=duration
                        )
                        await session.merge(scraped_entry)
                        await session.commit()

                    # Page content analysis
                    html = await page.content()
                    
                    # Keyword check (Simple & Robust)
                    if self.required_keywords:
                        found = False
                        for kw in self.required_keywords:
                            if kw.lower() in html.lower():
                                found = True
                                break
                        if not found:
                            print(f"[RSS_SCRAPER] [{self.name}] Skipping {url}: No required keywords {self.required_keywords} found.")
                            continue

                    if self.click_selector:
                        try:
                            print(f"[RSS_SCRAPER] [{self.name}] Click on: {self.click_selector}")
                            await self._click(page, self.click_selector)
                            # Update HTML after click
                            html = await page.content()
                        except Exception as e:
                            print(f"[RSS_SCRAPER] [{self.name}] Click failed: {e}")
                    
                    found_links = self._extract_links(html)
                    if found_links:
                        yield {"links": found_links, "override_filename": rss_title, "source_url": url}

                except Exception as e:
                    print(f"[RSS_SCRAPER] [{self.name}] Error processing {url}: {e}")

            await browser.close()

    async def _click(self, page: Page, selector: str):
        """Attempts to click using selector or fallback to text/role locator."""
        try:
            # 1. Try direct locator with timeout
            locator = page.locator(selector)
            if await locator.count() > 0:
                print(f"[RSS_SCRAPER] [{self.name}] Clicking 1: {selector}")
                await locator.first.click(timeout=8000)
                await page.wait_for_load_state("networkidle", timeout=5000)
                return

            # 2. Case-insensitive text fallback (If selector looks like simple text)
            clean_text = selector.replace("button:has-text('", "").replace("')", "").replace("'", "")
            if len(clean_text) < 30:
                print(f"[RSS_SCRAPER] [{self.name}] Clicking 2: {clean_text}")
                btn = page.get_by_role("button", name=re.compile(clean_text, re.IGNORECASE))
                if await btn.count() > 0:
                    await btn.first.click(timeout=8000)
                    await page.wait_for_load_state("networkidle", timeout=5000)
                    return

            raise Exception(f"Element not found: {selector}")
        except Exception as e:
            raise e

    def _extract_links(self, html: str) -> List[str]:
        all_found = []
        for pattern in self.target_patterns:
            all_found.extend(re.findall(pattern, html))
        
        return list(dict.fromkeys(all_found))
