import asyncio
import re
import time
from typing import List
from playwright.async_api import async_playwright
from app.core.config import settings

class LinkUnlocker:
    """
    Advanced Link Unlocker that uses the Webtop container 
    to bypass Cloudflare/Turnstile.
    """
    def __init__(self):
        pass

    async def unlock(self, url: str, extra_patterns: List[str] = None) -> List[str]:
        """Unlocks a dl-protect.link and returns the final file hoster links."""
        print(f"[UNLOCKER] Starting unlock process for: {url}")
        
        from app.services.browser_manager import browser_manager
        
        final_links = []
        async with async_playwright() as p:
            # Use browser_manager to handle Webtop lifecycle
            browser = await browser_manager.get_browser(p, url=url)
            if not browser:
                return []

            try:
                # Always use a NEW page for isolation
                page = await browser.new_page()

                # IMPORTANT: Force navigation to the target URL
                print(f"[UNLOCKER] Navigating to target URL: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)

                print(f"[UNLOCKER] Page title: '{await page.title()}'")
  
                # --- MultiUp Mirror Traversal ---
                if "multiup.io" in url:
                    print("[UNLOCKER] MultiUp page detected. Looking for mirror link...")
                    try:
                        # Wait a bit for the page to stabilize
                        await asyncio.sleep(3)
                        # Flexible search for /mirror/ (supports /fr/mirror/, /en/mirror/, etc.)
                        mirror_locator = page.locator('a[href*="/mirror/"], form[action*="/mirror/"]')
                        count = await mirror_locator.count()
                        if count > 0:
                            mirror_url = await mirror_locator.first.get_attribute("href") or await mirror_locator.first.get_attribute("action")
                            if mirror_url:
                                if not mirror_url.startswith("http"):
                                    from urllib.parse import urljoin
                                    mirror_url = urljoin(url, mirror_url)
                                print(f"[UNLOCKER] SUCCESS: Found mirror link ({mirror_url}). Navigating...")
                                await page.goto(mirror_url, wait_until="domcontentloaded", timeout=30000)
                        else:
                            print("[UNLOCKER] WARNING: No mirror link found on MultiUp page. Staying here.")
                    except Exception as me:
                        print(f"[UNLOCKER] MultiUp traversal error: {me}")
                
                # --- Zoneurs / ZT-Protect Traversal ---
                if "zoneurs.net" in url:
                    print("[UNLOCKER] Zoneurs.net detected. Waiting for unlock button...")
                    try:
                        unlock_btn = page.locator("#continueBtn")
                        await unlock_btn.wait_for(state="visible", timeout=15000)
                        print("[UNLOCKER] Clicking 'Déverrouiller le lien'...")
                        await unlock_btn.click()
                        
                        # Wait for the result input to appear and have a value
                        result_input = page.locator(".result-input")
                        await result_input.wait_for(state="visible", timeout=15000)
                        await asyncio.sleep(2) # Stability
                        
                        final_url = await result_input.get_attribute("value")
                        if final_url:
                            print(f"[UNLOCKER] SUCCESS: Link found in input: {final_url}")
                            # We can directly add it to final_links and skip the rest of the generic extraction if we want,
                            # but let's keep the flow standard by navigating to it or just adding it.
                            final_links.append(final_url)
                            await page.close()
                            return [final_url]
                    except Exception as ze:
                        print(f"[UNLOCKER] Zoneurs traversal error: {ze}")

                # Wait for the validation button (Turnstile success) - Skips if on MultiUp
                if "multiup.io" in page.url:
                    print("[UNLOCKER] MultiUp detected, skipping Turnstile check.")
                    solved = True
                else:
                    btn = page.locator("#subButton")
                    try:
                        print("[UNLOCKER] Waiting for Turnstile validation...")
                        await btn.wait_for(state="attached", timeout=15000)
                        await btn.wait_for(state="visible", timeout=15000)

                        # --- Multi-attempt strategy: Wait -> Reload -> Fallback Click ---
                        solved = False
                        for attempt in range(1, 3):
                            print(f"[UNLOCKER] Turnstile attempt {attempt}/2...")
                            attempt_start = time.time()
                            attempt_timeout = 25 # seconds per attempt
                            
                            while time.time() - attempt_start < attempt_timeout:
                                # 1. Detect the Turnstile Frame
                                cf_frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"], iframe[title*="Cloudflare"]').first
                                
                                # 2. Check if already solved (Success checkmark or button enabled)
                                is_success = await cf_frame.locator('#success:not([style*="display: none"])').is_visible()
                                if is_success or await btn.is_enabled():
                                    print(f"[UNLOCKER] Turnstile solved on attempt {attempt}!")
                                    solved = True
                                    break
                                
                                # 3. Fallback: Try a single click ONLY on the 2nd attempt after some waiting
                                if attempt == 2 and time.time() - attempt_start > 10:
                                    checkbox = cf_frame.locator('input[type="checkbox"], .ctp-checkbox-label').first
                                    if await checkbox.count() > 0 and await checkbox.is_visible():
                                        print("[UNLOCKER] Fallback: Clicking the Turnstile checkbox...")
                                        await checkbox.hover(timeout=5000)
                                        await checkbox.click(timeout=5000)
                                        await asyncio.sleep(5) # Give it time to register
                                        if await btn.is_enabled():
                                            solved = True
                                            break
                                
                                await asyncio.sleep(2)
                            
                            if solved:
                                break
                            
                            if attempt == 1:
                                print("[UNLOCKER] Still stuck. Reloading the page...")
                                try:
                                    await page.reload(wait_until="domcontentloaded", timeout=30000)
                                    await asyncio.sleep(5)
                                except Exception as err_reload:
                                    print(f"[UNLOCKER] Reload timeout (non-critical): {err_reload}")
                        
                        if not solved:
                            print("[UNLOCKER] WARNING: Turnstile challenge not solved after 2 attempts.")

                        print("[UNLOCKER] Clicking 'Continuer' button (auto-waiting for it to be enabled)...")
                        async with page.expect_navigation(timeout=60000):
                            # click() will wait for the button to be enabled (Turnstile solved)
                            await btn.click(timeout=60000)
                        
                        print("[UNLOCKER] Turnstile passed!")
                    except Exception as e:
                        print(f"[UNLOCKER] Turnstile step skipped or failed: {e}")

                # --- Final extraction (Common for all flows) ---
                print(f"[UNLOCKER] Reached final page: {page.url}")
                
                # MultiUp specific: wait for the mirror list to appear
                if "multiup.io" in page.url:
                    print("[UNLOCKER] MultiUp mirror page detected. Waiting for hoster links to load...")
                    try:
                        # Wait for a known hoster or the table
                        await page.wait_for_selector("a[href*='1fichier.com'], a[href*='rapidgator'], table", timeout=15000)
                        await asyncio.sleep(3) # Extra stability for dynamic elements
                    except Exception as e:
                        print(f"[UNLOCKER] Note: Timeout waiting for specific selectors ({e}). Proceeding with current content.")

                content = await page.content()
                total_extracted = 0
                
                # 1. Standard pattern matching
                patterns_to_check = extra_patterns if extra_patterns else list(settings.DIRECT_SCAN_PATTERNS)
                
                for pattern in patterns_to_check:
                    found = list(set(re.findall(pattern, content, re.IGNORECASE)))
                    if found:
                        print(f"[UNLOCKER] {len(found)} link(s) extracted from final page using pattern.")
                        final_links.extend(found)
                        total_extracted += len(found)

                if total_extracted == 0:
                    print(f"[UNLOCKER] WARNING: No links extracted from {page.url}")
                    print(f"[UNLOCKER] Page Title: '{await page.title()}'")
                    # print(f"[UNLOCKER] Content length: {len(content)}")
                
                # Close only the page, not the browser connection
                await page.close()
                
            except Exception as e:
                print(f"[UNLOCKER] Error during extraction: {e}")
                try:
                    if 'page' in locals() and page: await page.close()
                except: pass
                
        return sorted(list(set(final_links)))
