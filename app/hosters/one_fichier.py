import aiohttp
import re
from typing import Optional, Dict, Any
from app.core.utils import parse_size

class OneFichierService:
    """
    Direct verification for 1fichier.com
    Does not require an account. Use status codes and Regex.
    """
    @staticmethod
    async def check(url: str, session: Optional[aiohttp.ClientSession] = None) -> Dict[str, Any]:
        target_url = f"{url}&lg=fr" if "?" in url else f"{url}?lg=fr"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"
        }

        # Use an external session if provided, otherwise create a temporary one
        if session:
            return await OneFichierService._do_check(target_url, session, headers)
        else:
            async with aiohttp.ClientSession(headers=headers) as new_session:
                return await OneFichierService._do_check(target_url, new_session, {})

    @staticmethod
    async def _do_check(url: str, session: aiohttp.ClientSession, headers: Dict[str, str]) -> Dict[str, Any]:
        try:
            async with session.get(url, allow_redirects=True, timeout=15, headers=headers) as response:
                if response.status == 404:
                    return {"status": "dead", "host": "1fichier.com"}
                
                if response.status == 200:
                    html = await response.text()
                    
                    premium_block = re.search(r'<table class="premium".*?>(.*?)</table>', html, re.DOTALL | re.IGNORECASE)
                    
                    if premium_block:
                        content = premium_block.group(1)
                        name_match = re.search(r'font-weight:bold[^>]*>([^<]+)</span>', content, re.IGNORECASE)
                        size_match = re.search(r'font-style:italic[^>]*>([^<]+)</span>', content, re.IGNORECASE)
                        
                        if name_match and size_match:
                            name = name_match.group(1).strip()
                            size_str = size_match.group(1).strip()
                            return {
                                "status": "alive",
                                "filename": name,
                                "size": parse_size(size_str),
                                "host": "1fichier.com"
                            }
                        
                return {"status": "unknown", "host": "1fichier.com"}
        except Exception as e:
            return {"status": "error", "host": "1fichier.com", "error": str(e)}
