import aiohttp
import asyncio
from typing import Dict, List, Any
from app.core.config import settings

class AllDebridClient:
    def __init__(self, apikey: str = settings.ALLDEBRID_API_KEY):
        self.apikey = apikey
        self.base_url = "https://api.alldebrid.com/v4"
        self.agent = settings.ALLDEBRID_AGENT

    async def check_links(self, links: List[str]) -> Dict[str, dict]:
        """
        Check link availability via AllDebrid.
        Supports batching (100 links per request).
        """
        if not self.apikey:
            print("[ALLDEBRID] Warning: No API Key configured.")
            return {}

        if not links:
            return {}

        results = {}
        batch_size = 50
        
        async with aiohttp.ClientSession() as session:
            for i in range(0, len(links), batch_size):
                batch = links[i:i + batch_size]
                print(f"[ALLDEBRID] Checking availability of {len(batch)} links... (batch #{i//batch_size + 1})")
                
                try:
                    data = aiohttp.FormData()
                    for link in batch:
                        data.add_field('link[]', link)

                    async with session.post(
                        f"{self.base_url}/link/infos",
                        headers={"Authorization": f"Bearer {self.apikey}"},
                        params={"agent": self.agent},
                        data=data
                    ) as response:
                        if response.status != 200:
                            print(f"[ALLDEBRID] Batch #{i//batch_size + 1}: HTTP Error {response.status}")
                            continue

                        try:
                            response_data = await response.json()
                        except Exception:
                            body = await response.text()
                            print(f"[ALLDEBRID] Batch #{i//batch_size + 1}: Failed to parse JSON. Response: {body[:100]}...")
                            continue
                        
                        if response_data.get("status") == "success":
                            infos = response_data.get("data", {}).get("infos", [])
                            for j, original_link in enumerate(batch):
                                if j < len(infos):
                                    info = infos[j]
                                    results[original_link] = {
                                        "status": "alive" if not info.get("error") else "dead",
                                        "size": info.get("filesize") or info.get("size", 0),
                                        "filename": info.get("filename", ""),
                                        "host": info.get("host", ""),
                                        "supported": info.get("supported", True),
                                        "error": info.get("error")
                                    }
                                else:
                                    results[original_link] = {"status": "unknown"}
                            print(f"[ALLDEBRID] Batch #{i//batch_size + 1} processed successfully.")
                        else:
                            err = response_data.get("error", {})
                            print(f"[ALLDEBRID] Batch #{i//batch_size + 1}: API Error: {err.get('message', 'Unknown')}")
                            
                except asyncio.TimeoutError:
                    print(f"[ALLDEBRID] Batch #{i//batch_size + 1}: Timeout while checking links.")
                except Exception as e:
                    print(f"[ALLDEBRID] Batch #{i//batch_size + 1}: Exception ({type(e).__name__}): {str(e)}")

        return results

    async def unlock_link(self, link: str) -> Dict[str, Any]:
        """
        Unlock a single link via AllDebrid.
        Returns the unlocked link and metadata.
        """
        if not self.apikey:
            return {"status": "error", "error": "No API Key"}

        async with aiohttp.ClientSession() as session:
            try:
                params = {
                    "agent": self.agent,
                    "apikey": self.apikey,
                    "link": link
                }
                async with session.get(f"{self.base_url}/link/unlock", params=params) as response:
                    if response.status != 200:
                        return {"status": "error", "error": f"HTTP {response.status}"}
                    
                    data = await response.json()
                    return data
            except Exception as e:
                return {"status": "error", "error": str(e)}
