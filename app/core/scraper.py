import os
import asyncio
import httpx
import json
import re
import traceback
import feedparser
from typing import List, Optional, AsyncGenerator, Dict, Any, Union
from datetime import datetime, timezone
from jinja2 import Template
from jsonpath_ng.ext import parse
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from app.db.models import ScrapedURL
from app.db.database import get_db_ctx
from app.services.unlocker import LinkUnlocker
from app.core.config import settings

class Scraper:
    def __init__(self, config: dict):
        self._name = config.get("name", "Scraper")
        self.steps = config.get("steps", [])
        self.default_scrape_once = config.get("scrape_once", True)
        self.global_ignore_resolutions = config.get("ignore_resolutions", [])
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://www.google.com/",
            **config.get("headers", {})
        }
        self.timeout = config.get("timeout", 60)
        self.unlocker = LinkUnlocker()
        self._last_request_time = 0

    @property
    def name(self) -> str:
        return self._name

    async def run(self) -> AsyncGenerator[Dict[str, Any], None]:
        from playwright.async_api import async_playwright
        try:
            # Check if any step needs a browser to avoid starting it unnecessarily
            needs_browser = any(s.get("use_browser") for s in self.steps)
            
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                context = {
                    "settings": settings,
                    "now": datetime.now,
                    "today": datetime.now().strftime('%Y-%m-%d')
                }
                
                if needs_browser:
                    async with async_playwright() as p:
                        context["playwright"] = p
                        async for batch in self._execute_step(client, 0, context):
                            yield batch
                else:
                    async for batch in self._execute_step(client, 0, context):
                        yield batch
        except (GeneratorExit, asyncio.CancelledError):
            pass
        except Exception as e:
            print(f"[{self.name}] Error in run: {e}")
            traceback.print_exc()

    async def _execute_step(self, client: httpx.AsyncClient, step_idx: int, context: dict) -> AsyncGenerator[Dict[str, Any], None]:
        import time
        import random
        if step_idx >= len(self.steps):
            return

        step = self.steps[step_idx]
        step_name = step.get("name", f"step_{step_idx}")
        step_type = step.get("type", "html").lower()
        use_browser = step.get("use_browser", False)
        
        step_scrape_once = step.get("scrape_once", self.default_scrape_once)
        if step_idx == 0 and "scrape_once" not in step:
            step_scrape_once = False

        # Build URL(s) to process
        raw_url_field = step.get("url")
        if not raw_url_field and step_idx > 0:
            prev_step_name = self.steps[step_idx-1].get("name", f"step_{step_idx-1}")
            prev_data = context.get(prev_step_name, {})
            raw_url_field = prev_data.get("url") if isinstance(prev_data, dict) else prev_data
            
        urls_to_process = raw_url_field if isinstance(raw_url_field, list) else [raw_url_field]

        for raw_url in urls_to_process:
            current_page = step.get("pagination", {}).get("start_page", 1)
            while True:
                # Render URL with current page context
                page_context = {**context, "page": current_page, "index": current_page}
                url = self._render_string(raw_url, page_context)
                if not url or not url.startswith("http"):
                    break
                
                # Auto-inject pagination param if missing from rendered URL
                pag_config = step.get("pagination")
                if pag_config and pag_config.get("param") and current_page > 1:
                    p_name = pag_config["param"]
                    # Check if the parameter is already in the URL (either as template or raw)
                    if f"{p_name}=" not in url:
                        url = self._update_url_param(url, p_name, current_page)

                # Prevent making requests with empty crucial parameters (like ?title=) 
                # which often happen when a previous step failed to provide a value.
                if any(empty_param in url for empty_param in ["title=", "q=", "query=", "search="]):
                    if any(url.endswith(p) or f"{p}&" in url for p in ["title=", "q=", "query=", "search="]):
                        print(f"[{self.name}] [{step_name}] ⏭ Skipping URL with empty search parameter: {url}")
                        break

                if step_scrape_once:
                    async with get_db_ctx() as session:
                        stmt = select(ScrapedURL).where(ScrapedURL.url == url)
                        res = await session.execute(stmt)
                        if res.scalar_one_or_none():
                            print(f"[{self.name}] [{step_name}] Skipping already scraped URL: {url}")
                            # Skip this URL/page and move to next in pagination or next raw_url
                            break
                
                # NEW: Pre-check URL for ignored resolutions (only in the slug/filename part)
                step_ignore = step.get("ignore_resolutions", [])
                ignore_resolutions = list(set(settings.IGNORE_RESOLUTIONS + self.global_ignore_resolutions + step_ignore))
                if ignore_resolutions:
                    # Only check the last part of the URL path to avoid category names like /films-720p-et-1080p/
                    parsed_url = urlparse(url)
                    url_slug = parsed_url.path.split('/')[-1] or (parsed_url.path.split('/')[-2] if '/' in parsed_url.path else "")
                    
                    if any(re.search(rf'[\.\-\_]{re.escape(res)}[\.\-\_]', url_slug, re.I) or re.search(rf'{re.escape(res)}\b', url_slug, re.I) for res in ignore_resolutions):
                        print(f"[{self.name}] [{step_name}] ⏭ Skipping URL (Resolution ignored in slug): {url}")
                        break
                
                # Intelligent Throttling: only wait if we are actually going to fetch something
                # and if the minimum delay hasn't passed since the last request.
                delay = step.get("item_delay")
                # If no explicit delay, apply 1s default if we are in a follow-up step
                # or a list-based step (RSS/JSON)
                if delay is None and (step_idx > 0 or step_type in ["rss", "json"]):
                    delay = 1.0 # Default 1s delay
                
                if delay:
                    jitter = delay * 0.2
                    target_delay = delay + random.uniform(-jitter, jitter)
                    now = time.time()
                    elapsed = now - self._last_request_time
                    if elapsed < target_delay:
                        wait_time = target_delay - elapsed
                        await asyncio.sleep(wait_time)

                # Fetch content
                content = None
                step_headers = {**self.headers, **step.get("headers", {})}
                
                if use_browser:
                    content = await self._fetch_with_browser(url, step, context, step_headers)
                    self._last_request_time = time.time()
                else:
                    try:
                        print(f"[{self.name}] [{step_name}] Fetching URL: {url}")
                        self._last_request_time = time.time()
                        resp = await client.get(url, headers=step_headers)
                        resp.raise_for_status()
                        content = resp.text
                    except Exception as e:
                        print(f"[{self.name}] [{step_name}] Error fetching {url}: {e}")
                        break

                if not content: 
                    break

                if step.get("debug"):
                    debug_dir = os.path.join("data", "debug")
                    os.makedirs(debug_dir, exist_ok=True)
                    ts = int(time.time())
                    safe_step = step_name.replace(" ", "_")
                    debug_file = os.path.join(debug_dir, f"debug_{self.name}_{safe_step}_{ts}.txt")
                    try:
                        with open(debug_file, "w", encoding="utf-8") as f:
                            f.write(content)
                    except Exception as e:
                        print(f"[{self.name}] [{step_name}] DEBUG: Failed to save debug file: {e}")

                # Process results
                results = []
                page_info = f" (Page {current_page})" if step.get("pagination") else ""
                
                if step_type == "rss":
                    results = self._extract_rss(content)
                elif step_type == "json":
                    # Smart JSON extraction:
                    # 1. Get the list of items
                    items_path = step.get("items_path") or "$.results[*]"
                    if items_path:
                        items_path = self._render_string(items_path, context)
                    
                    try:
                        results = self._extract_json(content, items_path)
                    except Exception as e:
                        print(f"[{self.name}] [{step_name}]{page_info} JSON extraction error: {e}")
                        results = []

                    # 2. Apply filter if provided (can be JSONPath or a simple key=value)
                    filter_expr = step.get("filter")
                    if filter_expr and results:
                        filter_rendered = self._render_string(filter_expr, context)
                        # If it's a JSONPath filter like [?(@.key == val)], try to extract the logic
                        match = re.search(r'\[\?\(@\.(\w+)\s*==\s*(.+)\)\]', filter_rendered)
                        if match:
                            key, val = match.groups()
                            # Clean up quotes if any
                            val = val.strip("'\"")
                            # Try to match as int or string
                            results = [r for r in results if str(r.get(key)) == str(val)]
                        elif not filter_expr.startswith("$"):
                            # Simple key=value filter (not a full JSONPath)
                            if "==" in filter_rendered:
                                key, val = [p.strip() for p in filter_rendered.split("==", 1)]
                                results = [r for r in results if str(r.get(key)) == str(val)]
                        else:
                            # Fallback: try applying it as a full JSONPath filter if it's not already covered
                            try:
                                from jsonpath_ng.ext import parse
                                matches = parse(filter_rendered).find(results)
                                results = [m.value for m in matches]
                            except: pass
                    
                    # 3. Apply result_path if provided (e.g. $[0])
                    res_path = step.get("result_path")
                    if res_path and results:
                        try:
                            from jsonpath_ng.ext import parse
                            # Apply the path to the list of items found
                            matches = parse(res_path).find(results)
                            results = [m.value for m in matches]
                        except Exception as e:
                            print(f"[{self.name}] [{step_name}]{page_info} result_path error: {e}")
                
                if not results: 
                    # Use filter_expr if it was a search/filter step, otherwise items_path
                    f_val = step.get("filter") or step.get("items_path")
                    reason = f" (Filter: {f_val})" if step_type == "json" and f_val else ""
                    print(f"[{self.name}] [{step_name}]{page_info} No items found{reason}, skipping.")
                    break
                else:
                    # If results is already set by RSS or JSON branch, we don't overwrite it.
                    # Otherwise, handle generic HTML/text content or JS rendered content.
                    if not results:
                        if step.get("js_code") and use_browser:
                            try:
                                results = json.loads(content)
                                if not isinstance(results, list): results = [results]
                            except:
                                results = [content]
                        else:
                            results = [content]
 

                print(f"[{self.name}] [{step_name}]{page_info} Processing {len(results)} item(s)")
                import random
                # Iterate over results
                for i, item in enumerate(results):
                    new_context = context.copy()
                    
                    if isinstance(item, str):
                        item_data = {"content": item, "url": url}
                        text_to_check = item
                    elif isinstance(item, dict):
                        item_data = item.copy()
                        if "url" not in item_data: item_data["url"] = url
                        if "content" not in item_data: item_data["content"] = str(item)
                        text_to_check = str(item)
                    else:
                        item_data = {"content": str(item), "url": url}
                        text_to_check = str(item)
                    
                    new_context[step_name] = item_data
                    
                    # 1. Keyword & Resolution filtering
                    current_tags = []
                    
                    # 1a. Resolution filtering
                    step_ignore = step.get("ignore_resolutions", [])
                    ignore_resolutions = list(set(settings.IGNORE_RESOLUTIONS + self.global_ignore_resolutions + step_ignore))
                    
                    if ignore_resolutions:
                        title_to_check = item_data.get("title") or item_data.get("name") or ""
                        # If we have a title, check it first as it's more precise, otherwise check full text
                        check_target = title_to_check if title_to_check else text_to_check
                        
                        if any(re.search(rf'\b{re.escape(res)}\b', check_target, re.I) for res in ignore_resolutions):
                            label = title_to_check or "item"
                            print(f"[{self.name}] [{step_name}] ⏭ Skipping: {label} (Resolution {ignore_resolutions} ignored)")
                            continue

                    required_keywords = step.get("required_keywords", {})
                    if required_keywords:
                        match_found = False
                        for kw, tag in required_keywords.items():
                            if re.search(kw, text_to_check, re.IGNORECASE):
                                current_tags.append(tag)
                                match_found = True
                        if not match_found:
                            label = item_data.get("title") or item_data.get("name") or "item"
                            print(f"[{self.name}] [{step_name}] ⏭ Skipping: {label} (No keywords match)")
                            continue

                    # 2. Link extraction
                    raw_extracted = []
                    regex_patterns = step.get("regex_patterns", []) or step.get("dig_patterns", []) or step.get("dig_patterns_url", [])
                    hoster_patterns = step.get("hoster_patterns", [])
                    unlock_patterns = step.get("unlock_patterns", [])
                    
                    all_extract_patterns = list(set(regex_patterns + hoster_patterns + unlock_patterns))
                    
                    if all_extract_patterns:
                        for pat in all_extract_patterns:
                            matches = re.findall(pat, text_to_check)
                            for m in matches:
                                link = m[0] if isinstance(m, tuple) else m
                                if link.startswith("http") and link not in raw_extracted:
                                    raw_extracted.append(link)

                    if raw_extracted:
                        ignore_patterns = step.get("ignore_patterns", [])
                        if ignore_patterns:
                            filtered = []
                            for link in raw_extracted:
                                if any(re.search(pat, link) for pat in ignore_patterns):
                                    continue
                                filtered.append(link)
                            raw_extracted = filtered

                    if raw_extracted:
                        print(f"[{self.name}] [{step_name}] Found {len(raw_extracted)} link(s) to process")

                    # 3. Unlocking
                    final_links = []
                    for href in raw_extracted:
                        should_unlock = any(re.search(pat, href) for pat in unlock_patterns) if unlock_patterns else step.get("unlock_links", False)
                        if should_unlock:
                            print(f"[{self.name}] [{step_name}] Unlocking: {href}")
                            try:
                                unlocked = await self.unlocker.unlock(href, extra_patterns=regex_patterns)
                                if unlocked: final_links.extend(unlocked)
                            except:
                                pass
                        else:
                            final_links.append(href)

                    # 4. Yield or Follow
                    is_last_step = (step_idx == len(self.steps) - 1)
                    is_yield = step.get("yield_links")
                    should_yield = (is_last_step and is_yield is not False) or (is_yield is True)
                    
                    if should_yield:
                        valid_links = [l for l in final_links if isinstance(l, str) and l.startswith("http")]
                        if valid_links:
                            # Try to find a title/year in the context if not explicitly overridden
                            final_title = self._render_string(step.get("override_title"), new_context)
                            final_year = self._render_string(step.get("override_year"), new_context)

                            if not final_title or final_title == "None":
                                # Search backwards through steps to find a title
                                for prev_step in reversed(self.steps[:step_idx + 1]):
                                    prev_name = prev_step.get("name")
                                    if prev_name in new_context and isinstance(new_context[prev_name], dict):
                                        if new_context[prev_name].get("title"):
                                            final_title = new_context[prev_name]["title"]
                                            if not final_year or final_year == "None":
                                                final_year = new_context[prev_name].get("year")
                                            break
                            
                            if not final_title: final_title = "Untitled"
                            
                            print(f"[{self.name}] [{step_name}] 🚀 SUCCESS: Found {len(valid_links)} link(s) for '{final_title}'")
                            all_tags = list(set(context.get("__accumulated_tags__", []) + current_tags))
                            yield {
                                "links": list(set(valid_links)),
                                "source_url": url,
                                "override_title": final_title,
                                "override_year": str(final_year) if final_year and str(final_year).isdigit() else None,
                                "tags": all_tags
                            }

                    new_context["__accumulated_tags__"] = list(set(context.get("__accumulated_tags__", []) + current_tags))
                    is_follow = step.get("follow_links")
                    should_follow = (not is_last_step and is_follow is not False) or (is_follow is True)
                    
                    if should_follow:
                        # If we extracted links, we follow each of them
                        if raw_extracted:
                            for entry_link in raw_extracted:
                                next_context = new_context.copy()
                                # Preserve existing item data (like title, year) while updating URL for the next step
                                next_context[step_name] = {**item_data, "url": entry_link, "content": ""}
                                async for next_batch in self._execute_step(client, step_idx + 1, next_context):
                                    yield next_batch
                        else:
                            # Otherwise just move to next step with current context
                            async for next_batch in self._execute_step(client, step_idx + 1, new_context):
                                yield next_batch

                # Record that this URL has been scraped only AFTER the loop finished successfully
                if step_scrape_once and results:
                    async with get_db_ctx() as session:
                        stmt = select(ScrapedURL).where(ScrapedURL.url == url)
                        res = await session.execute(stmt)
                        if not res.scalar_one_or_none():
                            session.add(ScrapedURL(url=url, source_name=self.name))
                            await session.commit()
                
                if not step.get("pagination"): break
                current_page += 1
                if current_page > step.get("pagination", {}).get("max_pages", 999):
                    break

    async def _fetch_with_browser(self, url: str, step: dict, context: dict, headers: dict = None) -> Optional[str]:
        from playwright.async_api import async_playwright
        from app.services.browser_manager import browser_manager
        
        step_name = step.get("name", "browser_step")
        wait_for = step.get("wait_for")
        wait_until = step.get("wait_until", "domcontentloaded")
        
        print(f"[{self.name}] [{step_name}] Open page by browser: {url}")
        
        # Reuse existing playwright instance if available in context
        p_provided = context.get("playwright")
        
        async def _run_with_p(p):
            browser = await browser_manager.get_browser(p, url=url)
            if not browser: return None
            
            # Use the provided headers for the browser context
            fetch_headers = headers or self.headers
            context_pw = await browser.new_context(
                user_agent=fetch_headers.get("User-Agent", self.headers["User-Agent"]),
                extra_http_headers=fetch_headers
            )
            page = await context_pw.new_page()
            try:
                response = None
                try:
                    response = await page.goto(url, wait_until=wait_until, timeout=self.timeout * 1000)
                except Exception as e:
                    if "Download is starting" in str(e):
                        # Use request API to get the content if it's a download (RSS/JSON/XML)
                        # This avoids the error and gets the raw data directly
                        response_req = await page.request.get(url)
                        return await response_req.text()
                    raise e
                
                if wait_for:
                    wait_timeout = step.get("wait_timeout", 15)
                    try: 
                        # Use state="attached" because many links are in hidden inputs (not visible)
                        await page.wait_for_selector(wait_for, state="attached", timeout=wait_timeout * 1000)
                    except: 
                        print(f"[{self.name}] [{step_name}] Timeout waiting for '{wait_for}'")
                
                if step.get("click_selector"):
                    try:
                        await page.click(step["click_selector"])
                        await page.wait_for_load_state("networkidle", timeout=10000)
                    except: pass
                
                if step.get("js_code"):
                    rendered_js = self._render_string(step["js_code"], context)
                    # Pass the context as an argument to the JS function
                    result = await page.evaluate(rendered_js, context)
                    return json.dumps(result)
                
                # For RSS and JSON, we prefer the raw text from the response 
                # because page.content() often wraps non-HTML content in <html><body>...
                # or transforms it in ways that break parsers (like feedparser or json.loads).
                if step.get("type") in ["rss", "json"] and response:
                    try:
                        return await response.text()
                    except:
                        pass

                # If it's an RSS feed, sometimes content() wraps it in HTML
                # Better to get the raw body if it's not a standard HTML page
                content = await page.content()
                if step.get("type") == "rss" and "<?xml" in content and "<html>" in content:
                    # Try to extract the XML from the HTML wrapper if any
                    match = re.search(r'(<\?xml.*</rss>)', content, re.DOTALL | re.IGNORECASE)
                    if match:
                        return match.group(1)
                
                return content
            except Exception as e:
                print(f"[{self.name}] [{step_name}] Browser error: {e}")
                return None
            finally:
                await browser.close()

        if p_provided:
            return await _run_with_p(p_provided)
        else:
            async with async_playwright() as p:
                return await _run_with_p(p)

    def _extract_rss(self, content: str) -> List[Dict[str, Any]]:
        feed = feedparser.parse(content)
        return [dict(entry) for entry in feed.entries]

    def _extract_json(self, content: str, items_path: Optional[str]) -> List[Dict[str, Any]]:
        data = json.loads(content)
        if items_path:
            return [m.value for m in parse(items_path).find(data)]
        return [data] if isinstance(data, dict) else data

    def _render_string(self, template_str: str, context: dict) -> str:
        if not template_str or "{{" not in template_str:
            return template_str
        try:
            return Template(template_str).render(context)
        except:
            return template_str

    def _update_url_param(self, url: str, param: str, value: Any) -> str:
        parsed = urlparse(url)
        if param.startswith("/"):
            # Path-based pagination (e.g. /page/2/)
            clean_param = param.strip("/")
            # Remove any existing pagination segment from the path
            new_path = re.sub(rf"/{clean_param}/\d+", "", parsed.path)
            # Ensure it ends with /page/X/
            new_path = f"{new_path.rstrip('/')}/{clean_param}/{value}/"
            return urlunparse(parsed._replace(path=new_path))
            
        query = parse_qs(parsed.query)
        query[param] = [str(value)]
        return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
