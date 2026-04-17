import re
import asyncio
from typing import List, Optional, AsyncGenerator, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from playwright.async_api import async_playwright
from app.scrapers.base import BaseScraper
from app.db.models import ScrapedURL, DownloadLink
from app.core.config import settings
from app.services.unlocker import LinkUnlocker

class WebtopScraper(BaseScraper):
    """
    Advanced Scraper that uses Playwright (potentially via Webtop) 
    to handle complex JS-heavy sites and solve Cloudflare challenges.
    """
    def __init__(self, config: dict):
        self._name = config.get("name", "Webtop")
        self.entry_url = config.get("entry_url")
        self.entry_wait_for = config.get("entry_wait_for")
        
        # JS extraction snippets from config
        self.js_items = config.get("js_items")   # Script to find items in list
        self.js_links = config.get("js_links")   # Script to find links in detail
        
        # Link unlocking patterns (e.g., dl-protect.link)
        self.unlock_patterns = config.get("unlock_patterns", [])
        
        # Deduplication behavior
        self.scrape_once = config.get("scrape_once", True)
        
        # Specialized unlocker
        self.unlocker = LinkUnlocker()
        
        # Legacy support/fallback
        self.target_patterns = config.get("target_patterns", [])
        self.required_keywords = config.get("required_keywords", [])

    @property
    def name(self) -> str:
        return self._name

    async def _get_browser(self, playwright):
        """Uses BrowserManager to get a connection to the Webtop browser."""
        from app.services.browser_manager import browser_manager
        return await browser_manager.get_browser(playwright)

    async def run(self, session: Optional[AsyncSession] = None) -> AsyncGenerator[Dict[str, Any], None]:
        async with async_playwright() as p:
            browser = await self._get_browser(p)
            if not browser:
                print(f"[{self.name}] ABORTING: Browser not available.")
                return

            # Create a dedicated context (letting it use the browser's native UA)
            context = await browser.new_context()
            page = await context.new_page()
            
            try:
                # 1. Discovery Phase
                print(f"[{self.name}] Accessing entry URL: {self.entry_url}")
                # Use domcontentloaded + manual sleep to be more resilient to Cloudflare/Ads
                await page.goto(self.entry_url, wait_until="domcontentloaded", timeout=60000)
                
                # Wait for Cloudflare to settle
                print(f"[{self.name}] Waiting 10s for Cloudflare/JS challenges...")
                await asyncio.sleep(10)
                
                if self.entry_wait_for:
                    try: await page.wait_for_selector(self.entry_wait_for, timeout=15000)
                    except: print(f"[{self.name}] Warning: Wait selector '{self.entry_wait_for}' not found.")

                # Extract items
                items_to_process = []
                if self.js_items:
                    print(f"[{self.name}] Running js_items discovery...")
                    raw_items = await page.evaluate(self.js_items)
                    print(f"[{self.name}] Discovery found {len(raw_items or [])} raw items.")
                    print(f"[{self.name}] DEBUG - Raw items: {raw_items}")
                    for it in (raw_items or []):
                        if isinstance(it, str): items_to_process.append({"url": it})
                        elif isinstance(it, dict) and "href" in it: items_to_process.append(it)
                else:
                    print(f"[{self.name}] No js_items defined.")

                if not items_to_process:
                    print(f"[{self.name}] No items found.")
                    return

                # Deduplicate and filter already scraped (Only if scrape_once is True)
                if session and self.scrape_once:
                    urls = [it.get("href") or it.get("url") for it in items_to_process]
                    stmt = select(ScrapedURL.url).where(ScrapedURL.url.in_(urls))
                    result = await session.execute(stmt)
                    scraped_urls = set(r[0] for r in result.all())
                    
                    # Only process items not in DB
                    items_to_process = [it for it in items_to_process if (it.get("href") or it.get("url")) not in scraped_urls]

                print(f"[{self.name}] Found {len(items_to_process)} new items to process.")

                # 2. Detail & Extraction Phase
                for idx, item in enumerate(items_to_process, 1):
                    item_url = item.get("href") or item.get("url")
                    print(f"[{self.name}] Processing item {idx}/{len(items_to_process)}: {item_url}")
                    
                    try:
                        await page.goto(item_url, wait_until="domcontentloaded", timeout=45000)
                        await asyncio.sleep(5)
                        
                        # Extract links via JS
                        found_links = []
                        if self.js_links:
                            # Pass the item metadata (title, ep_added, etc) to the JS script
                            found_links = await page.evaluate(self.js_links, item)
                            print(f"[{self.name}] JS extracted {len(found_links or [])} potential links.")
                        
                        # Normalize found_links to list of objects { href, provider }
                        links_data = []
                        if isinstance(found_links, list):
                            for link in found_links:
                                if isinstance(link, str): links_data.append({"href": link})
                                else: links_data.append(link)
                        
                        if not links_data:
                            print(f"[{self.name}] No links found on detail page.")
                            continue

                        # 3. Handle Link Unlocking (dl-protect, etc.)
                        all_final_urls = []
                        for link_obj in links_data:
                            href = link_obj.get("href")
                            provider = link_obj.get("provider")
                            episode_label = link_obj.get("episode_label")
                            if not href: continue
                            
                            # 2.1 Deduplication: Skip if this specific protected link was already unlocked
                            if session:
                                stmt_dup = select(ScrapedURL).where(ScrapedURL.url == href)
                                if (await session.execute(stmt_dup)).scalar():
                                    print(f"[{self.name}] Skipping already processed link: {href}")
                                    continue
                            
                            # Match against unlock_patterns (Provider + Regex)
                            match_config = None
                            for upat in self.unlock_patterns:
                                target_prov = upat.get("provider", "").lower()
                                target_reg = upat.get("pattern", "")
                                
                                prov_match = not target_prov or (provider and target_prov in provider.lower())
                                href_match = re.search(target_reg, href)
                                
                                if prov_match and href_match:
                                    match_config = upat
                                    break

                            if match_config:
                                print(f"[{self.name}] Match found! Unlocking {provider} link: {href}")
                                try:
                                    # Use the specialized LinkUnlocker (internal Docker/Webtop flow)
                                    unlocked_urls = await self.unlocker.unlock(href)
                                    if unlocked_urls:
                                        # Record that this protected link is successfully handled
                                        if session:
                                            await session.merge(ScrapedURL(
                                                url=href, source_name=f"{self.name}-link", status="success",
                                                scrape_once=self.scrape_once, last_scraped=datetime.now(timezone.utc)
                                            ))
                                            await session.commit()
                                        
                                        # Determine individual link filename override (Purely based on scraper metadata)
                                        current_filename = f"{item.get('title')} {episode_label or ''}".strip()
                                        current_filename = current_filename.replace(" ", ".").replace("..", ".")
                                        
                                        # Yield EACH link group immediately to allow real-time progress
                                        yield {
                                            "links": unlocked_urls,
                                            "source_url": item_url,
                                            "override_title": f"{item.get('title')} {episode_label or ''}".strip(),
                                            "override_year": item.get("year")
                                        }
                                except Exception as e:
                                    print(f"[{self.name}] Specialized unlock failed for {href}: {e}")

                        # Record visit of the main detail page
                        if session:
                            await session.merge(ScrapedURL(
                                url=item_url, source_name=self.name, status="success",
                                scrape_once=self.scrape_once, last_scraped=datetime.now(timezone.utc)
                            ))
                            await session.commit()

                    except Exception as e:
                        print(f"[{self.name}] Error processing details of {item_url}: {e}")

            finally:
                await browser.close()
