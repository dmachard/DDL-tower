import os
import asyncio
import httpx
import json
import re
from typing import List, Optional, AsyncGenerator, Dict, Any, Union
from datetime import datetime, timezone
from jinja2 import Template
from jsonpath_ng.ext import parse
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from app.scrapers.base import BaseScraper
from app.db.models import ScrapedURL

class JSONScraper(BaseScraper):
    """
    Generic scraper that chains multiple JSON API requests.
    Configurable via YAML.
    """
    def __init__(self, config: dict):
        self._name = config.get("name", "JSONScraper")
        self.steps = config.get("steps", [])
        self.scrape_once = config.get("scrape_once", True)
        self.headers = config.get("headers", {})
        self.timeout = config.get("timeout", 30)

    @property
    def name(self) -> str:
        return self._name

    def _render_string(self, text: str, context: dict) -> str:
        if not text or "{{" not in text:
            return text
        
        # Merge context with environment variables for convenience
        full_context = context.copy()
        full_context.update(os.environ)
        
        # Inject global settings
        from app.core.config import settings
        full_context["settings"] = settings
        
        template = Template(text)
        return template.render(**full_context)

    def _extract_jsonpath(self, data: Any, path: str) -> Any:
        try:
            jsonpath_expr = parse(path)
            matches = [match.value for match in jsonpath_expr.find(data)]
            return matches
        except Exception as e:
            if "NoneType" not in str(e):
                print(f"[{self.name}] JSONPath error on '{path}': {e}")
            return []

    async def run(self, session: Optional[AsyncSession] = None) -> AsyncGenerator[Dict[str, Any], None]:
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            context = {}
            async for batch in self._execute_step(client, 0, context, session):
                yield batch

    def _update_url_param(self, url: str, param: str, value: Any) -> str:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        query[param] = [str(value)]
        new_query = urlencode(query, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    async def _execute_step(self, client: httpx.AsyncClient, step_idx: int, context: dict, session: Optional[AsyncSession]) -> AsyncGenerator[Dict[str, Any], None]:
        if step_idx >= len(self.steps):
            return

        step = self.steps[step_idx]
        step_name = step.get("name", f"step_{step_idx}")
        items_path = step.get("items_path")
        pagination = step.get("pagination")
        
        base_url = self._render_string(step.get("url", ""), context)
        if not base_url:
            return

        current_page = 1
        max_pages = 1
        if pagination:
            max_pages = pagination.get("max_pages", 1)

        while current_page <= max_pages:
            url = base_url
            if pagination:
                url = self._update_url_param(base_url, pagination.get("param", "page"), current_page)

            headers = self.headers.copy()
            if "headers" in step:
                for k, v in step["headers"].items():
                    headers[k] = self._render_string(v, context)

            # Check scrape_once
            if self.scrape_once and session and not items_path:
                stmt = select(ScrapedURL).where(ScrapedURL.url == url)
                res = await session.execute(stmt)
                if res.scalar():
                    print(f"[{self.name}] Skipping already scraped URL: {url}")
                    current_page += 1
                    continue

            print(f"[{self.name}] Executing step '{step_name}' (Page {current_page}/{max_pages}): {url}")

            try:
                start_time = datetime.now(timezone.utc)
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                duration = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

                if self.scrape_once and session and not items_path:
                    scraped_entry = ScrapedURL(url=url, source_name=self.name, status="success", scrape_once=True, last_scraped=datetime.now(timezone.utc), duration_ms=duration)
                    await session.merge(scraped_entry)
                    await session.commit()

                if pagination and current_page == 1:
                    total_path = pagination.get("total_path")
                    if total_path:
                        totals = self._extract_jsonpath(data, total_path)
                        if totals and isinstance(totals[0], int):
                            actual_total = totals[0]
                            max_pages = min(max_pages, actual_total)
                            print(f"[{self.name}] Pagination found: {actual_total} total pages (crawling up to {max_pages})")

            except Exception as e:
                print(f"[{self.name}] Error in step '{step_name}': {e}")
                break

            # 2. Extract items
            filter_path = step.get("filter")
            result_path = step.get("result_path")
            regex_patterns = step.get("regex_patterns", [])

            results = []
            if items_path:
                results = self._extract_jsonpath(data, items_path)
            elif filter_path:
                results = self._extract_jsonpath(data, self._render_string(filter_path, context))
            elif result_path:
                results = self._extract_jsonpath(data, result_path)
            else:
                results = [data]

            # 3. Process results
            for item in results:
                new_context = context.copy()
                new_context[step_name] = item

                yield_links_path = step.get("yield_links")
                extracted_links = []
                
                if yield_links_path:
                    links = self._extract_jsonpath(item, yield_links_path)
                    if links:
                        for l in links:
                            if isinstance(l, list): extracted_links.extend([str(i) for i in l if i])
                            elif l: extracted_links.append(str(l))

                if regex_patterns:
                    item_str = json.dumps(item)
                    for pattern in regex_patterns:
                        try:
                            matches = re.findall(pattern, item_str)
                            extracted_links.extend(matches)
                        except re.error: pass

                if extracted_links:
                    valid_links = [l for l in extracted_links if isinstance(l, str) and l.startswith("http")]
                    if valid_links:
                        # Handle tags (convert string to list if needed)
                        tags = step.get("tags", [])
                        if isinstance(tags, str):
                            tags = [tags]

                        yield {
                            "links": list(set(valid_links)),
                            "source_url": url,
                            "override_title": self._render_string(step.get("override_title", ""), new_context),
                            "override_year": str(self._render_string(step.get("override_year", ""), new_context)),
                            "tags": tags
                        }
                
                async for next_batch in self._execute_step(client, step_idx + 1, new_context, session):
                    yield next_batch
            
            if not pagination:
                break
            current_page += 1
