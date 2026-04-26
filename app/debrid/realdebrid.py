import aiohttp
import asyncio
from typing import Dict, List, Any
from app.core.config import settings

class RealDebridClient:
    def __init__(self, apikey: str = settings.REALDEBRID_API_KEY):
        self.apikey = apikey
        self.base_url = "https://api.real-debrid.com/rest/1.0/"

    async def check_links(self, links: List[str]) -> Dict[str, dict]:
        """
        Check link availability via Real-Debrid.
        Real-Debrid doesn't seem to support batching for /unrestrict/check, 
        so we run them in parallel.
        """
        if not self.apikey:
            print("[REALDEBRID] Warning: No API Key configured.")
            return {}

        if not links:
            return {}

        results = {}
        
        async with aiohttp.ClientSession() as session:
            async def check_single(link: str):
                try:
                    # Authentication is not required for /unrestrict/check
                    data = {"link": link}
                    async with session.post(
                        f"{self.base_url}unrestrict/check",
                        data=data
                    ) as response:
                        if response.status != 200:
                            try:
                                err_data = await response.json()
                                return link, {"status": "error", "error": err_data.get("error", f"HTTP {response.status}")}
                            except:
                                return link, {"status": "error", "error": f"HTTP {response.status}"}
                        
                        resp_data = await response.json()
                        return link, {
                            "status": "alive" if resp_data.get("supported") == 1 else "dead",
                            "size": resp_data.get("filesize", 0),
                            "filename": resp_data.get("filename", ""),
                            "host": resp_data.get("host", ""),
                            "supported": resp_data.get("supported") == 1
                        }
                except Exception as e:
                    return link, {"status": "error", "error": str(e)}

            tasks = [check_single(link) for link in links]
            check_results = await asyncio.gather(*tasks)
            
            for link, res in check_results:
                results[link] = res

        return results

    async def unlock_link(self, link: str) -> Dict[str, Any]:
        """
        Unlock a single link via Real-Debrid.
        Returns a structure compatible with the app's expectations.
        """
        if not self.apikey:
            return {"status": "error", "error": "No API Key"}

        async with aiohttp.ClientSession() as session:
            try:
                headers = {"Authorization": f"Bearer {self.apikey}"}
                data = {"link": link}
                async with session.post(
                    f"{self.base_url}unrestrict/link", 
                    headers=headers,
                    data=data
                ) as response:
                    if response.status != 200:
                        try:
                            err_data = await response.json()
                            return {"status": "error", "error": err_data.get("error", f"HTTP {response.status}")}
                        except:
                            return {"status": "error", "error": f"HTTP {response.status}"}
                    
                    resp_data = await response.json()
                    # Map Real-Debrid response to the format expected by the app (based on AllDebrid)
                    return {
                        "status": "success",
                        "data": {
                            "link": resp_data.get("download"),
                            "filename": resp_data.get("filename")
                        }
                    }
            except Exception as e:
                return {"status": "error", "error": str(e)}
