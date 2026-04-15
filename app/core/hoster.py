import asyncio
import aiohttp
from typing import List, Dict, Any
from urllib.parse import urlparse

from app.hosters.one_fichier import OneFichierService
from app.hosters.nitroflare import NitroflareService
from app.hosters.rapidgator import RapidgatorService
from app.services.alldebrid import AllDebridClient

class Hoster:
    """
    Orchestrates link verification by dispatching links to direct check services
    or falling back to AllDebrid for unsupported hosts.
    """
    def __init__(self):
        self.ad_client = AllDebridClient()
        self.direct_mappers = {
            "1fichier.com": OneFichierService,
            "nitroflare.com": NitroflareService,
            "rapidgator.net": RapidgatorService
        }

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
        ad_links = []
        results = {}

        # 1. Dispatch links
        for link in links:
            domain = self._get_domain(link)
            if domain in self.direct_mappers:
                direct_links.append((link, self.direct_mappers[domain]))
            else:
                ad_links.append(link)

        # 2. Execute direct checks in parallel
        if direct_links:
            print(f"[HOSTER] Checking {len(direct_links)} links directly...")
            async with aiohttp.ClientSession() as session:
                async def wrapped_check(link, mapper, session):
                    res = await mapper.check(link, session)
                    status = res.get("status", "unknown").upper()
                    filename = res.get("filename", "N/A")
                    print(f"[HOSTER] {mapper.__name__[:-7]} | {status} | {filename or link[:40]}")
                    return link, res

                tasks = [wrapped_check(link, mapper, session) for link, mapper in direct_links]
                for coro in asyncio.as_completed(tasks):
                    link, res = await coro
                    results[link] = res

        if ad_links:
            print(f"[HOSTER-MANAGER] Checking {len(ad_links)} links via AllDebrid fallback...")
            ad_results = await self.ad_client.check_links(ad_links)
            results.update(ad_results)

        return results
