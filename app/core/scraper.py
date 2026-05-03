import random
import re
import time
import asyncio
import os
import json
import traceback
import feedparser
import httpx
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple, AsyncGenerator, Union
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from jinja2 import Template
from jsonpath_ng.ext import parse as jsonpath_parse
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ScrapedURL
from app.db.database import get_db_ctx
from app.services.unlocker import LinkUnlocker
from app.core.config import settings

class Scraper:
    def __init__(self, config: dict):
        self.name = config.get("name", "Unknown")
        self.steps = config.get("steps", [])
        self.headers = config.get("headers", {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        self.timeout = config.get("timeout", 30)
        self.global_ignore_resolutions = config.get("ignore_resolutions", [])
        self.global_hoster_patterns = config.get("hoster_patterns", [
            r'https?://(?:www\.)?1fichier\.com/\?[^\s"\'<>]+',
            r'https?://(?:www\.)?rapidgator\.net/file/[^\s"\'<>]+'
        ])
        self.unlocker = LinkUnlocker()
        self._last_request_time = 0

    async def run(self) -> AsyncGenerator[Dict[str, Any], None]:
        if not self.steps:
            return

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            async for batch in self._execute_step(client, 0, {}):
                yield batch

    async def _execute_step(self, client: httpx.AsyncClient, step_idx: int, context: dict) -> AsyncGenerator[Dict[str, Any], None]:
        if step_idx >= len(self.steps):
            return

        step = self.steps[step_idx]
        step_name = step.get("name", f"step_{step_idx}")
        url_template = step.get("url")
        
        if not url_template:
            return

        # Render URL from context
        try:
            urls = []
            # If it's already a list, use it as is, otherwise render it
            if isinstance(url_template, list):
                urls = [self._render_string(u, context) for u in url_template]
            else:
                rendered = self._render_string(url_template, context)
                if isinstance(rendered, str) and rendered.startswith("[") and rendered.endswith("]"):
                    try:
                        urls = json.loads(rendered.replace("'", '"'))
                    except: urls = [rendered]
                else:
                    urls = [rendered]
            
            for url in urls:
                # Basic validation and filtering
                if not url or not url.startswith("http"): continue
                
                # Check if already scraped
                if step.get("scrape_once"):
                    async with get_db_ctx() as session:
                        stmt = select(ScrapedURL).where(ScrapedURL.url == url)
                        res = await session.execute(stmt)
                        if res.scalar_one_or_none():
                            print(f"[{self.name}] [{step_name}] Skipping already scraped URL: {url}")
                            continue

                # Global ignore resolutions check in URL
                ignore_resolutions = list(set(settings.IGNORE_RESOLUTIONS + self.global_ignore_resolutions + step.get("ignore_resolutions", [])))
                if ignore_resolutions:
                    parsed_url = urlparse(url)
                    url_slug = parsed_url.path.split('/')[-1] or (parsed_url.path.split('/')[-2] if '/' in parsed_url.path else "")
                    if any(re.search(rf'[\.\-\_]{re.escape(res)}[\.\-\_]', url_slug, re.I) or re.search(rf'{re.escape(res)}\b', url_slug, re.I) for res in ignore_resolutions):
                        print(f"[{self.name}] [{step_name}] ⏭ Skipping URL (Resolution ignored in slug): {url}")
                        continue

                # --- PAGINATION LOOP ---
                current_page = step.get("pagination", {}).get("start_page", 1)
                prev_content_hash = None

                while True:
                    # 1. Fetch
                    content = await self._get_content(client, url, step, context, step_idx)
                    if not content: break
                    
                    # Anti-infinite loop
                    c_hash = hash(content)
                    if c_hash == prev_content_hash: break
                    prev_content_hash = c_hash

                    # 2. Parse
                    results, page_info = self._parse_results(content, step, context, current_page)
                    if not results:
                        if step.get("type") in ["rss", "json"]: break
                        results = [content]

                    # 3. Handle Items
                    scraped_any = False
                    for item in results:
                        async for batch in self._handle_item(client, item, step, context, step_idx, url, page_info):
                            yield batch
                            scraped_any = True

                    # Cleanup/Record
                    if step.get("scrape_once") and scraped_any:
                        await self._record_scraped(url)

                    # Next page?
                    if not step.get("pagination"): break
                    current_page += 1
                    if current_page > step.get("pagination", {}).get("max_pages", 999): break
                    url = self._update_url_param(url, step["pagination"].get("param", "page"), current_page)

        except Exception as e:
            print(f"[{self.name}] [{step_name}] Step error: {e}")
            traceback.print_exc()

    # --- HELPERS ---

    async def _get_content(self, client, url, step, context, step_idx) -> Optional[str]:
        step_name = step.get("name", "step")
        use_browser = step.get("use_browser", False)
        
        # Delay
        delay = step.get("item_delay")
        if delay is None and (step_idx > 0 or step.get("type") in ["rss", "json"]): delay = 1.0
        if delay:
            elapsed = time.time() - self._last_request_time
            target = delay + random.uniform(-delay*0.2, delay*0.2)
            if elapsed < target: await asyncio.sleep(target - elapsed)

        self._last_request_time = time.time()
        headers = {**self.headers, **step.get("headers", {})}

        if use_browser:
            content = await self._fetch_with_browser(url, step, context, headers)
        else:
            try:
                print(f"[{self.name}] [{step_name}] Fetching URL: {url}")
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                content = resp.text
            except Exception as e:
                print(f"[{self.name}] [{step_name}] Error: {e}")
                return None

        if content and step.get("debug"):
            debug_file = f"data/debug/debug_{self.name}_{step_name.replace(' ','_')}_{int(time.time())}.txt"
            os.makedirs("data/debug", exist_ok=True)
            with open(debug_file, "w", encoding="utf-8") as f: f.write(content)

        return content

    def _parse_results(self, content: str, step: dict, context: dict, page: int) -> Tuple[List[Any], str]:
        step_type = step.get("type", "html")
        page_info = f" (Page {page})" if step.get("pagination") else ""
        results = []

        if step_type == "rss":
            results = self._extract_rss(content)
        elif step_type == "json":
            path = self._render_string(step.get("items_path") or "$.results[*]", context)
            try:
                results = self._extract_json(content, path)
                # Filter/Path logic
                f_expr = step.get("filter")
                if f_expr and results:
                    f_rend = self._render_string(f_expr, context)
                    if "==" in f_rend and not f_rend.startswith("$"):
                        k, v = [x.strip().strip("'\"") for x in f_rend.split("==", 1)]
                        results = [r for r in results if str(r.get(k)) == str(v)]
                    else:
                        try: results = [m.value for m in jsonpath_parse(f_rend).find(results)]
                        except: pass
                r_path = step.get("result_path")
                if r_path and results:
                    try: results = [m.value for m in jsonpath_parse(r_path).find(results)]
                    except: pass
            except: pass

        if not results and step.get("js_code") and step.get("use_browser"):
            try:
                results = json.loads(content)
                if not isinstance(results, list): results = [results]
            except: pass

        if results: print(f"[{self.name}] [{step.get('name') or 'step'}]{page_info} Processing {len(results)} item(s)")
        return results, page_info

    async def _handle_item(self, client, item, step, context, step_idx, url, page_info):
        step_name = step.get("name", "step")
        new_ctx = context.copy()
        
        # Prepare data
        if isinstance(item, str): item_data = {"content": item, "url": url}
        elif isinstance(item, dict):
            item_data = item.copy()
            if "url" not in item_data: item_data["url"] = url
            if "content" not in item_data: item_data["content"] = str(item)
        else: item_data = {"content": str(item), "url": url}
        
        text = item_data.get("content", "")
        
        # Add override title/year to item_data so they are available in context for next steps
        override_t = self._render_string(step.get("override_title"), new_ctx)
        if override_t and override_t != "None":
            item_data["title"] = override_t
        override_y = self._render_string(step.get("override_year"), new_ctx)
        if override_y and override_y != "None":
            item_data["year"] = override_y

        new_ctx[step_name] = item_data
        
        # 1. Filter
        ignore = list(set(settings.IGNORE_RESOLUTIONS + self.global_ignore_resolutions + step.get("ignore_resolutions", [])))
        if ignore:
            target = item_data.get("title") or item_data.get("name") or text
            if any(re.search(rf'\b{re.escape(res)}\b', target, re.I) for res in ignore): return

        current_tags = []
        if step.get("required_keywords"):
            tags = self._matches_keywords(text, step["required_keywords"], step.get("excluded_keywords", []))
            if tags is None: return
            current_tags.extend(tags)

        # 2. Extract
        raw = self._extract_links(text, list(set((step.get("regex_patterns") or step.get("dig_patterns") or step.get("dig_patterns_url") or []) + step.get("hoster_patterns", []) + step.get("unlock_patterns", []))))

        if step.get("ignore_patterns"):
            raw = [l for l in raw if not any(re.search(p, l) for p in step["ignore_patterns"])]

        # Unlock
        final = []
        upats = step.get("unlock_patterns", [])
        for h in raw:
            if upats and any(re.search(p, h) for p in upats) or step.get("unlock_links"):
                try:
                    u = await self.unlocker.unlock(h, extra_patterns=step.get("regex_patterns", []))
                    if u: final.extend(u)
                except: pass
            else: final.append(h)

        # 3. Success or Follow
        is_last = (step_idx == len(self.steps) - 1)
        if (is_last and step.get("yield_links") is not False) or step.get("yield_links") is True:
            valid = [l for l in final if isinstance(l, str) and l.startswith("http")]
            if valid:
                title = self._render_string(step.get("override_title"), new_ctx)
                year = self._render_string(step.get("override_year"), new_ctx)
                if not title or title == "None":
                    for ps in reversed(self.steps[:step_idx + 1]):
                        pn = ps.get("name")
                        if pn in new_ctx and isinstance(new_ctx[pn], dict) and new_ctx[pn].get("title"):
                            title = new_ctx[pn]["title"]
                            if not year or year == "None": year = new_ctx[pn].get("year")
                            break
                #title = title or "Untitled"
                print(f"[{self.name}] [{step_name}] Found {len(valid)} link(s)")
                acc = list(set(context.get("__accumulated_tags__", []) + current_tags))
                yield {"links": list(set(valid)), "source_url": url, "override_title": title, "override_year": str(year) if year and str(year).isdigit() else None, "tags": acc}

        new_ctx["__accumulated_tags__"] = list(set(context.get("__accumulated_tags__", []) + current_tags))
        if (not is_last and step.get("follow_links") is not False) or step.get("follow_links") is True:
            if raw:
                for l in raw:
                    nctx = new_ctx.copy()
                    nctx[step_name] = {**item_data, "url": l, "content": ""}
                    async for b in self._execute_step(client, step_idx + 1, nctx): yield b
            else:
                async for b in self._execute_step(client, step_idx + 1, new_ctx): yield b

    async def _fetch_with_browser(self, url: str, step: dict, context: dict, headers: dict = None) -> Optional[str]:
        from playwright.async_api import async_playwright
        from app.services.browser_manager import browser_manager
        step_name = step.get("name", "browser")
        print(f"[{self.name}] [{step_name}] Open page by browser: {url}")
        async with async_playwright() as p:
            browser = await browser_manager.get_browser(p, url=url)
            if not browser: return None
            ctx_pw = await browser.new_context(user_agent=headers.get("User-Agent", self.headers["User-Agent"]), extra_http_headers=headers)
            page = await ctx_pw.new_page()
            try:
                try: resp = await page.goto(url, wait_until=step.get("wait_until", "domcontentloaded"), timeout=self.timeout*1000)
                except Exception as e:
                    if "Download is starting" in str(e):
                        req = await page.request.get(url)
                        return await req.text()
                    raise e
                if step.get("wait_for"):
                    try: await page.wait_for_selector(step["wait_for"], state="attached", timeout=step.get("wait_timeout", 15)*1000)
                    except: pass
                if step.get("click_selector"):
                    try:
                        await page.click(step["click_selector"])
                        await page.wait_for_load_state("networkidle", timeout=10000)
                    except: pass
                if step.get("js_code"):
                    res = await page.evaluate(self._render_string(step["js_code"], context), context)
                    return json.dumps(res)
                if step.get("type") in ["rss", "json"] and resp:
                    try: return await resp.text()
                    except: pass
                return await page.content()
            except Exception as e:
                print(f"[{self.name}] [{step_name}] Browser error: {e}")
                return None
            finally: await browser.close()

    def _extract_rss(self, content: str) -> List[Dict[str, Any]]:
        return [dict(e) for e in feedparser.parse(content).entries]

    def _extract_json(self, content: str, path: Optional[str]) -> List[Dict[str, Any]]:
        data = json.loads(content)
        if path: return [m.value for m in jsonpath_parse(path).find(data)]
        return [data] if isinstance(data, dict) else data

    def _render_string(self, s: str, context: dict) -> str:
        if not s or "{{" not in s: return s
        try: return Template(s).render(context)
        except: return s

    def _update_url_param(self, url: str, param: str, value: Any) -> str:
        parsed = urlparse(url)
        if param.startswith("/"):
            clean = param.strip("/")
            path = re.sub(rf"/{clean}/\d+", "", parsed.path)
            path = f"{path.rstrip('/')}/{clean}/{value}/"
            return urlunparse(parsed._replace(path=path))
        query = parse_qs(parsed.query)
        query[param] = [str(value)]
        return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))

    def _extract_links(self, text: str, patterns: List[str]) -> List[str]:
        """Extracts unique HTTP links from text using a list of regex patterns."""
        if not text or not patterns: return []
        links = []
        for p in patterns:
            for m in re.findall(p, text):
                link = m[0] if isinstance(m, tuple) else m
                if link.startswith("http") and link not in links:
                    links.append(link)
        return links

    def _matches_keywords(self, text: str, required: Dict[str, str] = None, excluded: List[str] = None) -> Optional[List[str]]:
        if not text: return None
        tlow = text.lower()
        tags = []
        if required:
            found = False
            for kw, tag in required.items():
                if re.search(kw, tlow, re.IGNORECASE):
                    tags.append(tag)
                    found = True
            if not found: return None
        if excluded and any(re.search(kw, tlow, re.IGNORECASE) for kw in excluded): return None
        return tags

    def _is_hoster_link(self, link: str, patterns: List[str]) -> bool:
        return any(re.search(p, link) for p in patterns) if link and patterns else False

    async def _record_scraped(self, url: str):
        async with get_db_ctx() as session:
            stmt = select(ScrapedURL).where(ScrapedURL.url == url)
            res = await session.execute(stmt)
            if not res.scalar_one_or_none():
                session.add(ScrapedURL(url=url, source_name=self.name))
                await session.commit()
