import asyncio
import aiohttp
from typing import List, Dict, Any
from urllib.parse import urlparse

from app.hosters.one_fichier import OneFichierService
from app.hosters.nitroflare import NitroflareService
from app.hosters.rapidgator import RapidgatorService
from app.debrid.debrid import debrid_service

class Hoster:
    """
    Orchestrates link verification by dispatching links to direct check services
    or falling back to AllDebrid for unsupported hosts.
    """
    def __init__(self):
        self.debrid = debrid_service
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
        debrid_links = []
        results = {}

        # 1. Dispatch links
        for link in links:
            domain = self._get_domain(link)
            if domain in self.direct_mappers:
                direct_links.append((link, self.direct_mappers[domain]))
            else:
                debrid_links.append(link)

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
                    if res.get("status") == "alive":
                        results[link] = res
                    else:
                        # If direct check fails or is unknown, fallback to Debrid
                        print(f"[HOSTER] {link[:60]}... check {res.get('status') or 'failed'}. Falling back to Debrid.")
                        debrid_links.append(link)

        # 3. Check remaining links via Debrid service
        if debrid_links:
            print(f"[HOSTER] Checking {len(debrid_links)} links via Debrid...")
            ad_results = await self.debrid.check_links(debrid_links)
            results.update(ad_results)

        return results
