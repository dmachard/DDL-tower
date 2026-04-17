import re
import asyncio
import httpx
import feedparser
from typing import List, Optional, AsyncGenerator, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.scrapers.base import BaseScraper
from app.db.models import ScrapedURL
from app.core.config import settings

class ScnLogScraper(BaseScraper):
    """
    Specialized Scraper for ScnLog.me with multi-part support.
    Extracts ALL MultiUp links from a page and resolves them.
    """
    def __init__(self, config: dict):
        self._name = config.get("name", "ScnLog")
        self.rss_url = config.get("rss_url")
        self.scrape_once = config.get("scrape_once", True)
        from app.services.unlocker import LinkUnlocker
        self.unlocker = LinkUnlocker()

    @property
    def name(self) -> str:
        return self._name

    async def run(self, session: Optional[AsyncSession] = None) -> AsyncGenerator[Dict[str, Any], None]:
        if not self.rss_url:
            print(f"[{self.name}] No RSS URL configured.")
            return

        # 1. Fetch RSS entries
        items_to_process = []
        try:
            print(f"[{self.name}] Fetching RSS: {self.rss_url}")
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.get(self.rss_url, timeout=30)
                if resp.status_code == 200:
                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries:
                        url = entry.get("link")
                        title = entry.get("title", "")
                        if url:
                            items_to_process.append({"url": url, "title": title})
            
            print(f"[{self.name}] Found {len(items_to_process)} items in RSS.")
        except Exception as e:
            print(f"[{self.name}] RSS Error: {e}")

        # 2. Process each item
        async with httpx.AsyncClient(follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0"
        }) as client:
            for item in items_to_process:
                url = item["url"]
                title = item["title"]

                if session and self.scrape_once:
                    stmt = select(ScrapedURL).where(ScrapedURL.url == url)
                    res = await session.execute(stmt)
                    if res.scalar():
                        print(f"[{self.name}] Skipping already processed URL: {url}")
                        continue

                try:
                    print(f"[{self.name}] Visiting ScnLog: {url}")
                    resp = await client.get(url, timeout=30)
                    if resp.status_code != 200:
                        continue
                    
                    html_content = resp.text

                    # FIND ALL MultiUp links (handles multiple parts)
                    multiup_links = list(set(re.findall(r'https?://multiup\.io/download/[^"\'\s<>]+', html_content)))
                    if not multiup_links:
                        print(f"[{self.name}] No MultiUp links found on page.")
                        continue

                    print(f"[{self.name}] Found {len(multiup_links)} MultiUp part(s). Resolving...")
                    
                    all_resolved_links = []
                    for m_url in sorted(multiup_links): # Sort to keep part order if possible
                        print(f"[{self.name}] Unlocking part: {m_url}")
                        resolved = await self.unlocker.unlock(m_url)
                        if resolved:
                            all_resolved_links.extend(resolved)

                    # Deduplicate and Clean EVERYTHING
                    import html
                    final_links = []
                    seen_links = set()
                    for l in all_resolved_links:
                        clean = html.unescape(l).strip()
                        if clean and clean not in seen_links:
                            final_links.append(clean)
                            seen_links.add(clean)

                    if final_links:
                        print(f"[{self.name}] SUCCESS: Extracted {len(final_links)} total links.")
                        yield {
                            "links": final_links,
                            "override_filename": title,
                            "source_url": url,
                            "tags": []
                        }
                    
                    if session:
                        scraped_entry = ScrapedURL(
                            url=url, source_name=self.name, status="success",
                            scrape_once=self.scrape_once, last_scraped=datetime.now(timezone.utc)
                        )
                        await session.merge(scraped_entry)
                        await session.commit()

                except Exception as e:
                    print(f"[{self.name}] Error processing {url}: {e}")
