import re
import asyncio
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright
from app.core.utils import parse_size

class OneFichierService:
    """
    Direct verification for 1fichier.com using Playwright (Browser-based).
    This is necessary because 1fichier blocks IPv4 requests that don't solve 
    their specific Javascript challenge (Error #122).
    """
    @staticmethod
    async def check(url: str, session: Optional[Any] = None) -> Dict[str, Any]:
        # Strip all parameters including affiliate
        if "&" in url:
            url = url.split("&")[0]
            
        target_url = f"{url}&lg=fr" if "?" in url else f"{url}?lg=fr"
        print(f"[1FICHIER] Browser-based check for: {target_url}")

        from app.services.browser_manager import browser_manager

        try:
            async with async_playwright() as p:
                # Connect to the Webtop browser
                browser = await browser_manager.get_browser(p, url=target_url)
                if not browser:
                    return {"status": "error", "host": "1fichier.com", "error": "Could not connect to browser"}

                try:
                    # Use a NEW page for isolation
                    page = await browser.new_page()

                    # Navigation with retry for net::ERR_ABORTED
                    max_retries = 2
                    for attempt in range(max_retries + 1):
                        try:
                            await page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
                            break
                        except Exception as e:
                            if "net::ERR_ABORTED" in str(e) and attempt < max_retries:
                                print(f"[1FICHIER] Navigation aborted, retrying ({attempt+1}/{max_retries})...")
                                await asyncio.sleep(2)
                                continue
                            raise e

                    # Wait for stability (important for #122)
                    await asyncio.sleep(5)
                    
                    # Check if we are still on the error page
                    content = await page.content()
                    if "error #122" in content.lower() or "Javascript" in content:
                        print("[1FICHIER] Browser also blocked by #122. Trying to wait more...")
                        await asyncio.sleep(10)
                        content = await page.content()

                    # Check for 404
                    if "Not Found" in await page.title() or "demande n'existe pas" in content:
                        await page.close()
                        return {"status": "dead", "host": "1fichier.com"}

                    # Look for the premium table which contains file info
                    premium_table = page.locator('table.premium').first
                    if await premium_table.count() > 0:
                        html = await premium_table.inner_html()
                        
                        name_match = re.search(r'font-weight:bold[^>]*>([^<]+)</span>', html, re.DOTALL | re.IGNORECASE)
                        size_match = re.search(r'font-style:italic[^>]*>([^<]+)</span>', html, re.DOTALL | re.IGNORECASE)
                        
                        if name_match and size_match:
                            name = name_match.group(1).strip()
                            size_str = size_match.group(1).strip()
                            await page.close()
                            return {
                                "status": "alive",
                                "filename": name,
                                "size": parse_size(size_str),
                                "host": "1fichier.com"
                            }
                    
                    await page.close()
                    return {"status": "unknown", "host": "1fichier.com", "error": "Info table not found after bypass"}

                except Exception as e:
                    # We don't close the browser here anymore, just let the context exit
                    # or close the page if it exists
                    try:
                        if 'page' in locals() and page: await page.close()
                    except: pass
                    raise e

        except Exception as e:
            print(f"[1FICHIER] Browser Error: {str(e)}")
            return {"status": "error", "host": "1fichier.com", "error": str(e)}
