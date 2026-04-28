import asyncio
import aiohttp
from typing import List, Dict, Any
from urllib.parse import urlparse

from app.hosters.one_fichier import OneFichierService
from app.hosters.nitroflare import NitroflareService
from app.hosters.rapidgator import RapidgatorService
from app.debrid.debrid import debrid_service
from app.core.config import settings

class Hoster:
    """
    Orchestrates link verification by dispatching links to direct check services.
    Includes concurrency limiting to avoid crashing the browser infrastructure.
    """
    def __init__(self):
        self.debrid = debrid_service
        self.direct_mappers = {
            "1fichier.com": OneFichierService,
            "nitroflare.com": NitroflareService,
            "rapidgator.net": RapidgatorService
        }
        # Limit browser-based checks to concurrent tasks to save CPU/Memory
        self.semaphore = asyncio.Semaphore(settings.CONCURRENT_HOSTER_CHECKS)

    def _get_domain(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except:
            return ""

    async def check_links(self, links: List[str]) -> Dict[str, Any]:
        """
        Unified verification entry point. 
        Returns a dict mapping link -> info_dict.
        """
        if not links:
            return {}

        direct_links = []
        results = {}

        # 1. Dispatch links
        for link in links:
            domain = self._get_domain(link)
            if domain in self.direct_mappers:
                direct_links.append((link, self.direct_mappers[domain]))
            else:
                results[link] = {
                    "status": "unknown",
                    "host": domain or "unknown",
                    "filename": None,
                    "size": 0
                }

        # 2. Execute direct checks with concurrency limit
        if direct_links:
            print(f"[HOSTER] Checking {len(direct_links)} links with concurrency limit...")
            async with aiohttp.ClientSession() as session:
                async def wrapped_check(link, mapper, session):
                    # We use the semaphore to block if 3 tasks are already running
                    async with self.semaphore:
                        try:
                            res = await mapper.check(link, session)
                            status = res.get("status", "unknown").upper()
                            filename = res.get("filename", "N/A")
                            print(f"[HOSTER] {mapper.__name__[:-7]} | {status} | {filename or link[:40]}")
                            return link, res
                        except Exception as e:
                            print(f"[HOSTER] {mapper.__name__[:-7]} | ERROR | {link[:40]}: {e}")
                            return link, {"status": "error", "error": str(e)}

                tasks = [wrapped_check(link, mapper, session) for link, mapper in direct_links]
                # We still run them together, but the semaphore inside will serialize them
                for coro in asyncio.as_completed(tasks):
                    link, res = await coro
                    results[link] = res

        return results
