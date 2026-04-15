import aiohttp
import re
from typing import Optional, Dict, Any
from app.core.utils import parse_size

class NitroflareService:
    """
    Direct verification for nitroflare.com
    """
    @staticmethod
    async def check(url: str, session: Optional[aiohttp.ClientSession] = None) -> Dict[str, Any]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5"
        }

        if session:
            return await NitroflareService._do_check(url, session, headers)
        else:
            async with aiohttp.ClientSession(headers=headers) as new_session:
                return await NitroflareService._do_check(url, new_session, {})

    @staticmethod
    async def _do_check(url: str, session: aiohttp.ClientSession, headers: Dict[str, str]) -> Dict[str, Any]:
        try:
            async with session.get(url, allow_redirects=True, timeout=15, headers=headers) as response:
                if response.status == 404:
                    return {"status": "dead", "host": "nitroflare.com"}
                
                if response.status == 200:
                    html = await response.text()
                    
                    if "has been removed" in html or "File not found" in html or "file was deleted" in html:
                        return {"status": "dead", "host": "nitroflare.com"}
                    
                    # Name extraction from span[title]
                    name_match = re.search(r'<span title="([^"]+)">', html, re.IGNORECASE)
                    
                    # Size extraction from span[dir="ltr"]
                    size_match = re.search(r'<span dir="ltr"[^>]*>([^<]+)</span>', html, re.IGNORECASE)
                    
                    if name_match and size_match:
                        name = name_match.group(1).strip()
                        size_str = size_match.group(1).strip()
                        return {
                            "status": "alive",
                            "filename": name,
                            "size": parse_size(size_str),
                            "host": "nitroflare.com"
                        }

                return {"status": "unknown", "host": "nitroflare.com"}
        except Exception as e:
            return {"status": "error", "host": "nitroflare.com", "error": str(e)}
