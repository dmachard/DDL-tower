import aiohttp
import re
from typing import Optional, Dict, Any
from app.core.utils import parse_size

class RapidgatorService:
    """
    Direct verification for rapidgator.net
    Strictly forbids redirects to catch dead links that redirect to premium pages.
    """
    @staticmethod
    async def check(url: str, session: Optional[aiohttp.ClientSession] = None) -> Dict[str, Any]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5"
        }

        if session:
            return await RapidgatorService._do_check(url, session, headers)
        else:
            async with aiohttp.ClientSession(headers=headers) as new_session:
                return await RapidgatorService._do_check(url, new_session, {})

    @staticmethod
    async def _do_check(url: str, session: aiohttp.ClientSession, headers: Dict[str, str]) -> Dict[str, Any]:
        try:
            # We strictly forbid redirects to see 302s to /article/premium (Dead links)
            async with session.get(url, allow_redirects=False, timeout=15, headers=headers) as response:
                if response.status in (301, 302, 303, 307, 308):
                    return {"status": "dead", "host": "rapidgator.net", "error": f"Redirected to {response.headers.get('Location')}"}
                
                if response.status == 404:
                    return {"status": "dead", "host": "rapidgator.net"}
                
                if response.status == 200:
                    html = await response.text()
                    
                    if "404 File not found" in html or "Page not found" in html:
                        return {"status": "dead", "host": "rapidgator.net"}
                    
                    # Name extraction
                    name_match = re.search(r'Downloading:.*?<a[^>]*>([^<]+)</a>', html, re.DOTALL | re.IGNORECASE)
                    
                    # Size extraction
                    size_match = re.search(r'File size:.*?<strong>([^<]+)</strong>', html, re.DOTALL | re.IGNORECASE)
                    
                    if name_match and size_match:
                        name = name_match.group(1).strip()
                        size_str = size_match.group(1).strip()
                        return {
                            "status": "alive",
                            "filename": name,
                            "size": parse_size(size_str),
                            "host": "rapidgator.net"
                        }
                    
                    if "File size:" in html:
                        sizes = re.findall(r'(\d+[\.,]?\d*)\s*(Go|Mo|GB|MB|KB)', html, re.IGNORECASE)
                        if sizes:
                            val, unit = sizes[0]
                            return {
                                "status": "alive",
                                "size": parse_size(f"{val} {unit}"),
                                "host": "rapidgator.net"
                            }
                        return {"status": "alive", "host": "rapidgator.net"}
                        
                    if "challenges.cloudflare.com" in html or "turnstile" in html:
                        return {"status": "unknown", "host": "rapidgator.net", "error": "Cloudflare Challenge"}

                return {"status": "unknown", "host": "rapidgator.net"}
        except Exception as e:
            return {"status": "error", "host": "rapidgator.net", "error": str(e)}
