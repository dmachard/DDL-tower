import aiohttp
import asyncio
from typing import List, Dict, Any
from app.core.config import settings

class BestDebridClient:
    def __init__(self, apikey: str = settings.BESTDEBRID_API_KEY):
        self.apikey = apikey
        self.base_url = "https://bestdebrid.com/api/v1/"

    async def check_links(self, links: List[str]) -> Dict[str, dict]:
        """
        Check link availability via BestDebrid.
        BestDebrid doesn't have a dedicated check endpoint, 
        so we can only verify if the hoster is supported.
        Generating links just to check would be wasteful.
        """
        if not self.apikey:
            return {}

        results = {}
        try:
            # We fetch supported hosts to at least know if we CAN debrid them
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": self.apikey}
                async with session.get(f"{self.base_url}hosts", headers=headers) as response:
                    if response.status == 200:
                        hosts_data = await response.json()
                        # hosts_data is a list of dicts with 'domains'
                        supported_domains = set()
                        for h in hosts_data:
                            for d in h.get('domains', []):
                                supported_domains.add(d.lower())
                        
                        for link in links:
                            domain = link.split('//')[-1].split('/')[0].lower()
                            # Check if domain or any suffix matches
                            is_supported = False
                            for sd in supported_domains:
                                if domain == sd or domain.endswith('.' + sd):
                                    is_supported = True
                                    break
                            
                            results[link] = {
                                "status": "unknown", # We don't know if it's dead or alive without generating
                                "supported": is_supported,
                                "message": "BestDebrid (Check not supported)"
                            }
                    else:
                        print(f"[BESTDEBRID] Error fetching hosts: {response.status}")
        except Exception as e:
            print(f"[BESTDEBRID] Error checking links: {e}")

        return results

    async def unlock_link(self, link: str) -> Dict[str, Any]:
        """
        Unrestrict a link using BestDebrid.
        """
        if not self.apikey:
            return {"status": "error", "error": "No API Key"}

        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": self.apikey}
                data = {"link": link}
                async with session.post(
                    f"{self.base_url}generateLink",
                    headers=headers,
                    data=data
                ) as response:
                    if response.status != 200:
                        return {"status": "error", "error": f"HTTP {response.status}"}
                    
                    resp_data = await response.json()
                    if resp_data.get("error") == 0:
                        return {
                            "status": "success",
                            "data": {
                                "link": resp_data.get("link"),
                                "filename": resp_data.get("filename")
                            }
                        }
                    else:
                        return {"status": "error", "error": resp_data.get("message", "Unknown error")}
        except Exception as e:
            return {"status": "error", "error": str(e)}
