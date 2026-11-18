import asyncio
import re
import aiohttp
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

from app.debrid.debrid import debrid_service
from app.core.config import settings
from app.core.utils import parse_size


class GenericHoster:
    """Declarative hoster checker configured via config.yaml (HTTP, Browser+JS, POST form, or yt-dlp)."""

    def __init__(self, cfg: Dict[str, Any]):
        self.name = cfg.get("name", "Generic")
        self.domains = [d.lower() for d in (cfg.get("domains") or [])]
        self.use_browser = bool(cfg.get("use_browser", False))
        self.yt_dlp = bool(cfg.get("yt_dlp", False))
        self.allow_redirects = cfg.get("allow_redirects", True)
        self.dead_status = set(cfg.get("dead_if_status") or [404])
        self.dead_patterns = [p.lower() for p in (cfg.get("dead_if_text") or [])]
        self.error_patterns = [p.lower() for p in (cfg.get("error_if_text") or [])]
        self.retry_patterns = [p.lower() for p in (cfg.get("retry_if_text") or [])]
        self.alive_patterns = [p.lower() for p in (cfg.get("alive_if_text") or [])]
        self.filename_regex = cfg.get("extract-filename_regex")
        self.size_regex = cfg.get("extract-size_regex")
        self.extract_js = cfg.get("extract_js")
        self.size_from_post = cfg.get("size_from_post")
        self.wait_after_load = float(cfg.get("wait_after_load", 1))
        self.timeout = int(cfg.get("timeout", 15))

    def _extract_from_html(self, html: str, host: str) -> Optional[Dict[str, Any]]:
        filename = None
        size_bytes = 0
        if self.filename_regex:
            patterns = self.filename_regex if isinstance(self.filename_regex, list) else [self.filename_regex]
            for pat in patterns:
                m = re.search(pat, html, re.DOTALL | re.IGNORECASE)
                if m:
                    filename = m.group(1).strip()
                    break
        if self.size_regex:
            patterns = self.size_regex if isinstance(self.size_regex, list) else [self.size_regex]
            for pat in patterns:
                m = re.search(pat, html, re.DOTALL | re.IGNORECASE)
                if m:
                    val = m.group(1).strip()
                    size_bytes = int(val) if val.isdigit() else parse_size(val)
                    break
        if filename or size_bytes or any(p in html.lower() for p in self.alive_patterns):
            res = {"status": "alive", "host": host, "size": size_bytes}
            if filename:
                res["filename"] = filename
            return res
        return None

    async def check(self, url: str, session: Optional[aiohttp.ClientSession] = None) -> Dict[str, Any]:
        host = urlparse(url).netloc.lower().removeprefix("www.")

        if self.yt_dlp:
            return await self._check_ytdlp(url, host)
        if self.use_browser:
            return await self._check_browser(url, host)
        return await self._check_http(url, host, session)

    async def _check_ytdlp(self, url: str, host: str) -> Dict[str, Any]:
        try:
            import yt_dlp
            loop = asyncio.get_event_loop()

            def extract():
                with yt_dlp.YoutubeDL({"format": "best", "quiet": True, "no_warnings": True}) as ydl:
                    return ydl.extract_info(url, download=False)

            info = await loop.run_in_executor(None, extract)
            title = info.get("title")
            if title:
                ext = info.get("ext", "mp4")
                return {"status": "alive", "filename": f"{title}.{ext}".replace("/", "_"), "size": 0, "host": host}
            return {"status": "unknown", "host": host}
        except Exception as e:
            return {"status": "error", "host": host, "error": str(e)}

    async def _check_browser(self, url: str, host: str) -> Dict[str, Any]:
        from playwright.async_api import async_playwright
        from app.services.browser_manager import browser_manager

        page = None
        try:
            async with async_playwright() as p:
                browser = await browser_manager.get_browser(p, url=url)
                if not browser:
                    return {"status": "error", "host": host, "error": "Could not connect to browser"}
                page = await browser.new_page()
                for attempt in range(3):
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                        break
                    except Exception as e:
                        if "net::ERR_ABORTED" in str(e) and attempt < 2:
                            await asyncio.sleep(2)
                            continue
                        raise

                await asyncio.sleep(self.wait_after_load)
                html = await page.content()
                title = await page.title()

                for pat in self.retry_patterns:
                    if pat in html.lower():
                        await asyncio.sleep(10)
                        html = await page.content()
                        title = await page.title()
                        break

                combined_low = f"{title}\n{html}".lower()
                if any(p in combined_low for p in self.dead_patterns):
                    await page.close()
                    return {"status": "dead", "host": host}

                if self.extract_js:
                    data = await page.evaluate(self.extract_js)
                    if data and data.get("name"):
                        await page.close()
                        size_val = data.get("sizeStr") or ""
                        return {
                            "status": "alive",
                            "filename": data["name"].strip(),
                            "size": parse_size(size_val) if size_val else 0,
                            "host": host,
                        }

                parsed = self._extract_from_html(html, host)
                if parsed:
                    await page.close()
                    return parsed

                from app.core.utils import save_error_dump
                ss, hp = await save_error_dump(url, page)
                await page.close()
                return {"status": "error", "host": host, "error": "Info not found", "screenshot_path": ss, "html_path": hp}
        except Exception as e:
            ss, hp = None, None
            if page:
                try:
                    from app.core.utils import save_error_dump
                    ss, hp = await save_error_dump(url, page)
                    await page.close()
                except Exception:
                    pass
            return {"status": "error", "host": host, "error": str(e), "screenshot_path": ss, "html_path": hp}

    async def _check_http(self, url: str, host: str, session: Optional[aiohttp.ClientSession]) -> Dict[str, Any]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        own_session = session is None
        if own_session:
            session = aiohttp.ClientSession(headers=headers)
        try:
            async with session.get(url, allow_redirects=self.allow_redirects, timeout=self.timeout, headers=headers) as resp:
                if resp.status in self.dead_status:
                    return {"status": "dead", "host": host, "error": f"HTTP {resp.status}"}
                if resp.status != 200:
                    return {"status": "unknown", "host": host}
                html = await resp.text(errors="replace")

            html_low = html.lower()
            if any(p in html_low for p in self.dead_patterns):
                return {"status": "dead", "host": host}
            if any(p in html_low for p in self.error_patterns):
                return {"status": "error", "host": host, "error": "Challenge/Blocked"}

            parsed = self._extract_from_html(html, host)
            if not parsed:
                return {"status": "unknown", "host": host}

            if self.size_from_post and not parsed.get("size") and parsed.get("filename"):
                try:
                    file_id = url.rstrip("/").split("/")[-1]
                    id_rx = self.size_from_post.get("id_regex")
                    if id_rx:
                        m = re.search(id_rx, html, re.IGNORECASE)
                        if m:
                            file_id = m.group(1).strip()
                    data = {
                        k: v.replace("{{ id }}", file_id).replace("{{ filename }}", parsed["filename"])
                        for k, v in (self.size_from_post.get("data") or {}).items()
                    }
                    async with session.post(url, data=data, allow_redirects=True, timeout=self.timeout, headers=headers) as pr:
                        if pr.status == 200:
                            phtml = await pr.text(errors="replace")
                            for pat in (self.size_from_post.get("extract-size_regex") or []):
                                sm = re.search(pat, phtml, re.IGNORECASE)
                                if sm:
                                    val = sm.group(1).strip()
                                    parsed["size"] = int(val) if val.isdigit() else parse_size(val)
                                    break
                except Exception:
                    pass

            return parsed
        except Exception as e:
            return {"status": "error", "host": host, "error": str(e)}
        finally:
            if own_session:
                await session.close()


class Hoster:
    """
    Orchestrates link verification by dispatching links to YAML-configured hosters.
    """
    def __init__(self):
        self.debrid = debrid_service
        self.direct_mappers: Dict[str, Any] = {}
        for cfg in settings.HOSTERS:
            if cfg.get("enable", True):
                generic = GenericHoster(cfg)
                for dom in generic.domains:
                    self.direct_mappers[dom] = generic
        self.semaphore = asyncio.Semaphore(settings.CONCURRENT_HOSTER_CHECKS)

    def _get_domain(self, url: str) -> str:
        try:
            return urlparse(url).netloc.lower().removeprefix("www.")
        except Exception:
            return ""

    async def check_links(self, links: List[str]) -> Dict[str, Any]:
        if not links:
            return {}

        direct_links = []
        results = {}

        for link in links:
            domain = self._get_domain(link)
            if domain in self.direct_mappers:
                direct_links.append((link, self.direct_mappers[domain]))
            else:
                results[link] = {"status": "unknown", "host": domain or "unknown", "filename": None, "size": 0}

        if direct_links:
            print(f"[HOSTER] Checking {len(direct_links)} links...")
            async with aiohttp.ClientSession() as session:
                async def wrapped_check(link, mapper):
                    async with self.semaphore:
                        label = getattr(mapper, "name", None) or mapper.__name__[:-7]
                        try:
                            res = await mapper.check(link, session)
                            status = res.get("status", "unknown").upper()
                            filename = res.get("filename", "N/A")
                            print(f"[HOSTER] {label} | {status} | {filename or link[:40]}")
                            return link, res
                        except Exception as e:
                            print(f"[HOSTER] {label} | ERROR | {link[:40]}: {e}")
                            return link, {"status": "error", "error": str(e)}

                tasks = [wrapped_check(link, mapper) for link, mapper in direct_links]
                for coro in asyncio.as_completed(tasks):
                    link, res = await coro
                    results[link] = res

        return results
