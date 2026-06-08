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
        self.config = config
        self.name = config.get("name", "Unknown")
        self.enabled = config.get("enable") if config.get("enable") is not None else True
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
            async for batch in self._execute_step(client, 0, [{}]):
                yield batch

    async def _execute_step(self, client: httpx.AsyncClient, step_idx: int, contexts: List[dict]) -> AsyncGenerator[Dict[str, Any], None]:
        if step_idx >= len(self.steps) or not contexts:
            return

        step = self.steps[step_idx]
        step_name = step.get("name", f"step_{step_idx}")
        url_template = step.get("url")
        
        if not url_template:
            return

        # 1. Prepare all target URLs for this batch
        to_process = [] # List of (url, context)
        for ctx in contexts:
            try:
                rendered = self._render_string(url_template, ctx)
                urls = []
                if isinstance(rendered, str) and rendered.startswith("[") and rendered.endswith("]"):
                    try: urls = json.loads(rendered.replace("'", '"'))
                    except Exception: urls = [rendered]
                elif isinstance(rendered, list): urls = rendered
                else: urls = [rendered]
                
                for u in urls:
                    if u and u.startswith("http"):
                        to_process.append({"url": u, "ctx": ctx})
            except Exception: pass

        if not to_process:
            return

        # 2. Bulk check for scrape_once/scrape_one/cooldown
        final_list = []
        skipped_count = 0
        cooldown_hours = step.get("cooldown_hours") or step.get("scrape_cooldown_hours")
        
        if step.get("scrape_once") or step.get("scrape_one") or cooldown_hours is not None:
            all_urls = [i["url"] for i in to_process]
            async with get_db_ctx() as session:
                if cooldown_hours is not None:
                    from datetime import timedelta
                    stmt = select(ScrapedURL).where(ScrapedURL.url.in_(all_urls))
                    res = await session.execute(stmt)
                    scraped_records = {r.url: r for r in res.scalars().all()}
                    
                    now = datetime.now(timezone.utc)
                    cooldown_delta = timedelta(hours=float(cooldown_hours))
                    
                    for item in to_process:
                        url = item["url"]
                        record = scraped_records.get(url)
                        if record:
                            last_scraped = record.last_scraped
                            if last_scraped.tzinfo is None:
                                last_scraped = last_scraped.replace(tzinfo=timezone.utc)
                            
                            if now - last_scraped < cooldown_delta:
                                skipped_count += 1
                                continue
                        final_list.append(item)
                else:
                    stmt = select(ScrapedURL.url).where(ScrapedURL.url.in_(all_urls))
                    res = await session.execute(stmt)
                    already_scraped = set(res.scalars().all())
                    
                    for item in to_process:
                        if item["url"] in already_scraped:
                            skipped_count += 1
                        else:
                            final_list.append(item)
        else:
            final_list = to_process

        if skipped_count > 0:
            print(f"[{self.name}] [{step_name}] {len(final_list)} new URL(s) to visit ({skipped_count} skipped by scrape_once/cooldown)")
        elif step_idx > 0: # Only print for non-root steps to avoid noise
            print(f"[{self.name}] [{step_name}] Processing {len(final_list)} URL(s)")

        # 3. Process the remaining URLs
        for item in final_list:
            url = item["url"]
            ctx = item["ctx"]

            # Global ignore resolutions check in URL
            ignore_resolutions = list(set(settings.IGNORE_RESOLUTIONS + self.global_ignore_resolutions + step.get("ignore_resolutions", [])))
            if ignore_resolutions:
                parsed_url = urlparse(url)
                url_slug = parsed_url.path.split('/')[-1] or (parsed_url.path.split('/')[-2] if '/' in parsed_url.path else "")
                if any(re.search(rf'[\.\-\_]{re.escape(res)}[\.\-\_]', url_slug, re.I) or re.search(rf'{re.escape(res)}\b', url_slug, re.I) for res in ignore_resolutions):
                    print(f"[{self.name}] [{step_name}] ⏭ Skipping URL (Resolution ignored in slug): {url}")
                    continue

            try:
                # --- PAGINATION LOOP ---
                current_page = step.get("pagination", {}).get("start_page", 1)
                prev_content_hash = None
    
                while True:
                    if step.get("pagination"):
                        url = self._update_url_param(url, step["pagination"].get("param", "page"), current_page)
                    
                    # 1. Fetch
                    content = await self._get_content(client, url, step, ctx, step_idx)
                    if not content: break
                    
                    # Anti-infinite loop
                    c_hash = hash(content)
                    if c_hash == prev_content_hash: break
                    prev_content_hash = c_hash
    
                    # 2. Parse
                    results, page_info = self._parse_results(content, step, ctx, current_page, url)
                    if not results:
                        if step.get("type") in ["rss", "json"]: break
                        results = [content]
    
                    # 3. Handle Items
                    next_batch_contexts = []
                    for item_res in results:
                        async for res_or_ctx in self._handle_item(client, item_res, step, ctx, step_idx, url, page_info):
                            if isinstance(res_or_ctx, dict) and "links" in res_or_ctx:
                                yield res_or_ctx
                            else:
                                next_batch_contexts.append(res_or_ctx)
                    
                    # Recursion in batch
                    if next_batch_contexts:
                        async for b in self._execute_step(client, step_idx + 1, next_batch_contexts):
                            yield b
    
                    # Cleanup/Record
                    if step.get("scrape_once") or cooldown_hours is not None:
                        await self._record_scraped(url)
    
                    # Next page?
                    if not step.get("pagination"): break
                    current_page += 1
                    if current_page > step.get("pagination", {}).get("max_pages", 999): break

            except Exception as e:
                err_msg = str(e).strip() or type(e).__name__
                print(f"[{self.name}] [{step_name}] URL error ({url}): {err_msg}")
                try:
                    await self._record_scraped(url, status=f"failed: {err_msg[:100]}")
                except RuntimeError:
                    pass

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
                raise e

        if content and step.get("debug"):
            debug_file = f"data/debug/debug_{self.name}_{step_name.replace(' ','_')}_{int(time.time())}.txt"
            os.makedirs("data/debug", exist_ok=True)
            with open(debug_file, "w", encoding="utf-8") as f: f.write(content)

        return content

    def _parse_results(self, content: str, step: dict, context: dict, page: int, url: str = "") -> Tuple[List[Any], str]:
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
                        except Exception: pass
                r_path = step.get("result_path")
                if r_path and results:
                    try: results = [m.value for m in jsonpath_parse(r_path).find(results)]
                    except Exception: pass
            except Exception: pass

        if not results and step.get("js_code") and step.get("use_browser"):
            try:
                results = json.loads(content)
                if not isinstance(results, list): results = [results]
            except Exception: pass

        if results: 
            url_info = f" from {url}" if url else ""
            print(f"[{self.name}] [{step.get('name') or 'step'}]{page_info} Processing {len(results)} item(s){url_info}")
            for i, r in enumerate(results):
                r_str = str(r).replace('\n', ' ').replace('\r', '')
                print(f"  -> Item {i+1}: {r_str[:250]}{'...' if len(r_str) > 250 else ''}")
        return results, page_info

    async def _handle_item(self, client, item, step, context, step_idx, url, page_info):
        step_name = step.get("name", "step")
        new_ctx = context.copy()
        
        # Prepare data
        if isinstance(item, str): item_data = {"content": item, "url": url}
        elif isinstance(item, dict):
            item_data = item.copy()
            # Normalize common RSS/JSON keys to ensure 'url' and 'title' are available
            if "url" not in item_data:
                item_data["url"] = item_data.get("link") or item_data.get("href") or url
            if "title" not in item_data and "name" in item_data:
                item_data["title"] = item_data["name"]
            if "content" not in item_data: item_data["content"] = str(item)
            if "year" not in item_data:
                pub_parsed = item_data.get("published_parsed")
                if pub_parsed:
                    try: item_data["year"] = str(pub_parsed.tm_year)
                    except Exception: pass
                elif item_data.get("published"):
                    m = re.match(r'^(\d{4})', str(item_data["published"]))
                    if m: item_data["year"] = m.group(1)
                elif item_data.get("updated"):
                    m = re.match(r'^(\d{4})', str(item_data["updated"]))
                    if m: item_data["year"] = m.group(1)
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

        # Check item-level scraped_url deduplication
        db_url = item_data.get("scraped_url")
        if db_url:
            async with get_db_ctx() as session:
                stmt = select(ScrapedURL).where(ScrapedURL.url == db_url)
                if (await session.execute(stmt)).scalar_one_or_none():
                    print(f"[{self.name}] [{step_name}] Skipping item (already in database): {db_url}")
                    return
        
        # 1. Filter
        ignore = list(set(settings.IGNORE_RESOLUTIONS + self.global_ignore_resolutions + step.get("ignore_resolutions", [])))
        if ignore:
            target = item_data.get("title") or item_data.get("name") or text
            for res in ignore:
                if re.search(rf'\b{re.escape(res)}\b', target, re.I):
                    display = item_data.get("title") or item_data.get("name") or item_data.get("url") or (text[:100] + "...")
                    print(f"[{self.name}] [{step_name}] Item ignored (Resolution: {res}): {display}")
                    return

        current_tags = []
        if step.get("required_keywords"):
            tags = self._matches_keywords(text, step["required_keywords"], step.get("excluded_keywords", []))
            if tags is None:
                print(f"[{self.name}] [{step_name}] Item skipped (Keywords not matched) {step['required_keywords']}")
                return
            current_tags.extend(tags)

        # 2. Extract
        if isinstance(item, dict) and item_data.get("url") != url:
            raw = [item_data["url"]]
        else:
            patterns = list(set((step.get("regex_patterns") or step.get("dig_patterns") or step.get("dig_patterns_url") or []) + step.get("hoster_patterns", []) + step.get("unlock_patterns", [])))
            for u in settings.UNLOCKERS:
                patterns.extend(u.get("patterns", []))
            
            if not patterns and text.strip().startswith("http"):
                raw = [text.strip()]
            else:
                raw = self._extract_links(text, patterns)

        # Deduplicate links (e.g. .rar vs .rar.html)
        raw = self._deduplicate_links(raw)

        if step.get("ignore_patterns"):
            raw = [l for l in raw if not any(re.search(p, l) for p in step["ignore_patterns"])]

        print(f"[{self.name}] [{step_name}] Extracted links: {raw} for title: {item_data.get('title')}")

        # Unlock
        final = []
        upats = step.get("unlock_patterns", [])
        global_upats = []
        for u in settings.UNLOCKERS:
            global_upats.extend(u.get("patterns", []))
            
        for h in raw:
            is_unlockable = (upats and any(re.search(p, h) for p in upats)) or \
                            (global_upats and any(re.search(p, h) for p in global_upats)) or \
                            step.get("unlock_links")
            if is_unlockable:
                print(f"[{self.name}] [{step_name}] is_unlockable: {is_unlockable} for {h}")
                # OPTIMIZATION: Check if this intermediate link was already scraped/unlocked
                db_url = item_data.get("scraped_url") or h
                already_unlocked = False
                async with get_db_ctx() as session:
                    stmt = select(ScrapedURL).where(ScrapedURL.url == db_url)
                    if (await session.execute(stmt)).scalar_one_or_none():
                        already_unlocked = True
                
                if already_unlocked:
                    print(f"[{self.name}] [{step_name}] Skipping unlock (already in database): {db_url}")
                    continue


                try:
                    u = await self.unlocker.unlock(h, extra_patterns=step.get("hoster_patterns", []))
                    if u: 
                        final.extend(u)
                        # Record success to avoid re-unlocking this specific link
                        await self._record_scraped(db_url)
                except Exception: pass
            else: final.append(h)

        # 3. Success or Follow
        is_last = (step_idx == len(self.steps) - 1)
        if (is_last and step.get("yield_links") is not False) or step.get("yield_links") is True:
            valid = [l for l in final if isinstance(l, str) and l.startswith("http")]
            if valid:
                title = self._render_string(step.get("override_title"), new_ctx)
                year = self._render_string(step.get("override_year"), new_ctx)
                poster_url = None
                if not title or title == "None":
                    for ps in reversed(self.steps[:step_idx + 1]):
                        pn = ps.get("name")
                        if pn in new_ctx and isinstance(new_ctx[pn], dict) and new_ctx[pn].get("title"):
                            title = new_ctx[pn]["title"]
                            if not year or year == "None": year = new_ctx[pn].get("year")
                            break
                
                for ps in reversed(self.steps[:step_idx + 1]):
                    pn = ps.get("name")
                    if pn in new_ctx and isinstance(new_ctx[pn], dict):
                        thumb_list = new_ctx[pn].get("media_thumbnail")
                        if thumb_list and isinstance(thumb_list, list) and len(thumb_list) > 0:
                            poster_url = thumb_list[0].get("url")
                            break
                        elif new_ctx[pn].get("thumbnail"):
                            poster_url = new_ctx[pn]["thumbnail"]
                            break
                        elif new_ctx[pn].get("image"):
                            poster_url = new_ctx[pn]["image"]
                            break
                
                print(f"[{self.name}] [{step_name}] Found {len(valid)} link(s)")
                acc = list(set(context.get("__accumulated_tags__", []) + current_tags))
                yield {
                    "links": list(set(valid)), 
                    "source_url": url, 
                    "override_title": title, 
                    "override_year": str(year) if year and str(year).isdigit() else None, 
                    "tags": acc, 
                    "auto_download": step.get("auto_download", False),
                    "auto_download_years": step.get("auto_download_years"),
                    "auto_download_keywords": step.get("auto_download_keywords"),
                    "auto_download_resolutions": step.get("auto_download_resolutions"),
                    "category": step.get("category"),
                    "poster_url": poster_url
                }
                item_scraped_url = item_data.get("scraped_url")
                if item_scraped_url:
                    await self._record_scraped(item_scraped_url)
            elif is_last:
                print(f"[{self.name}] [{step_name}] No matching links found.")

        new_ctx["__accumulated_tags__"] = list(set(context.get("__accumulated_tags__", []) + current_tags))
        if (not is_last and step.get("follow_links") is not False) or step.get("follow_links") is True:
            if raw:
                for l in raw:
                    nctx = new_ctx.copy()
                    nctx[step_name] = {**item_data, "url": l, "content": ""}
                    yield nctx
            else:
                yield new_ctx

    async def _fetch_with_browser(self, url: str, step: dict, context: dict, headers: dict = None) -> Optional[str]:
        from playwright.async_api import async_playwright
        from app.services.browser_manager import browser_manager
        step_name = step.get("name", "browser")
        print(f"[{self.name}] [{step_name}] Open page by browser: {url}")
        async with async_playwright() as p:
            browser = await browser_manager.get_browser(p, url=url)
            if not browser: return None
            if browser.contexts:
                ctx_pw = browser.contexts[0]
            else:
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
                    except Exception: pass
                if step.get("click_selector"):
                    try:
                        await page.click(step["click_selector"])
                        await page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception: pass
                if step.get("js_code"):
                    res = await page.evaluate(self._render_string(step["js_code"], context), context)
                    return json.dumps(res)
                if step.get("type") in ["rss", "json"] and resp:
                    try: return await resp.text()
                    except Exception: pass
                return await page.content()
            except Exception as e:
                print(f"[{self.name}] [{step_name}] Browser error: {e}")
                raise e
            finally:
                try: await page.close()
                except Exception: pass
                try: await browser.close()
                except Exception: pass

    def _extract_rss(self, content: str) -> List[Dict[str, Any]]:
        feed = feedparser.parse(content)
        results = []
        for e in feed.entries:
            item = dict(e)
            # Ensure title and link are easily accessible in the dict
            if 'title' not in item and hasattr(e, 'title'): item['title'] = e.title
            if 'link' not in item and hasattr(e, 'link'): item['link'] = e.link
            results.append(item)
        return results

    def _extract_json(self, content: str, path: Optional[str]) -> List[Dict[str, Any]]:
        data = json.loads(content)
        if path: return [m.value for m in jsonpath_parse(path).find(data)]
        return [data] if isinstance(data, dict) else data

    def _render_string(self, s: str, context: dict) -> str:
        if not s or "{{" not in s: return s
        try: return Template(s).render(context)
        except Exception: return s

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

    def _deduplicate_links(self, links: List[str]) -> List[str]:
        """
        Generic deduplication: cleans URLs by removing query parameters 
        and truncating anything after known media/archive extensions.
        """
        if not links: return []
        
        # Known "good" extensions to stop at
        valid_exts = ['.rar', '.zip', '.7z', '.mkv', '.mp4', '.avi', '.ts', '.iso']
        unique_by_base = {}
        
        for url in links:
            # 1. Handle base URL and Query params
            if '1fichier.com' in url and '?' in url:
                # For 1fichier, the ID is in the query, keep only the first part of it
                base = url.split('?')[0] + '?' + url.split('?')[1].split('&')[0]
            else:
                # For others, remove query parameters entirely
                base = url.split('?')[0]
            
            base = base.rstrip('/')
            
            # 2. Truncate after the first "valid" extension found
            # (e.g. file.rar.html -> file.rar)
            low_base = base.lower()
            for ext in valid_exts:
                idx = low_base.rfind(ext)
                if idx != -1:
                    base = base[:idx + len(ext)]
                    break
            
            if base not in unique_by_base:
                unique_by_base[base] = url
            else:
                # Priority: keep the shortest URL
                if len(url) < len(unique_by_base[base]):
                    unique_by_base[base] = url
                    
        return list(unique_by_base.values())

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

    async def _record_scraped(self, url: str, status: str = "success"):
        print(f"[{self.name}] [DB] Recording URL in database: {url} (status: {status})")
        async with get_db_ctx() as session:
            stmt = select(ScrapedURL).where(ScrapedURL.url == url)
            res = await session.execute(stmt)
            existing = res.scalar_one_or_none()
            if existing:
                existing.status = status
                existing.last_scraped = datetime.now(timezone.utc)
            else:
                session.add(ScrapedURL(url=url, source_name=self.name, status=status))
            await session.commit()
