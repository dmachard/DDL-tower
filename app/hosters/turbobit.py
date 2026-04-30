import asyncio
import re
from typing import Optional, Dict, Any
from app.core.utils import parse_size
from app.core.config import settings

class TurbobitService:
    """
    Browser-based verification for turbobit.net
    """
    @staticmethod
    async def check(url: str, session: Any = None) -> Dict[str, Any]:
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            # Use a stealthy browser context
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                print(f"[TURBOBIT] Browser-based check for: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                
                # Give it a few seconds to bypass any basic JS checks
                await asyncio.sleep(3)
                
                html = await page.content()
                
                if "File not found" in html or "file was deleted" in html.lower():
                    await browser.close()
                    return {"status": "dead", "host": "turbobit.net"}

                # Extract filename and size using JS for better reliability
                data = await page.evaluate("""
                    () => {
                        let name = "";
                        let sizeStr = "";
                        
                        // Try different common selectors for Turbobit
                        const titleEl = document.querySelector('title');
                        const h1El = document.querySelector('h1');
                        const fileInfo = document.querySelector('.file-info');
                        
                        if (h1El) name = h1El.innerText;
                        else if (titleEl) name = titleEl.innerText;
                        
                        // Clean up "Download file" prefixes
                        name = name.replace(/Download file/i, "").replace(/Download/i, "").trim();
                        
                        const spans = Array.from(document.querySelectorAll('span'));
                        const sizeSpan = spans.find(s => s.innerText.match(/\\d+[.,]?\\d*\\s*(Gb|Mb|Kb|B)/i));
                        if (sizeSpan) sizeStr = sizeSpan.innerText;
                        
                        return { name, sizeStr };
                    }
                """)
                
                name = data.get("name")
                size_str = data.get("sizeStr")
                
                await browser.close()
                
                if name and ("turbobit" not in name.lower() or len(name) > 15):
                    return {
                        "status": "alive",
                        "filename": name,
                        "size": parse_size(size_str) if size_str else 0,
                        "host": "turbobit.net"
                    }
                
                return {"status": "unknown", "host": "turbobit.net"}
            except Exception as e:
                await browser.close()
                return {"status": "error", "host": "turbobit.net", "error": str(e)}
