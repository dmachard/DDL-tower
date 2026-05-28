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

            max_attempts = 3
            for attempt in range(1, max_attempts + 1):
                if attempt > 1:
                    print(f"[UNLOCKER] Retry attempt {attempt}/{max_attempts} for: {url}")
                
                try:
                    # Always use a NEW page for isolation
                    page = await browser.new_page()
                    
                    # --- Auto-close all popups at Chromium level ---
                    async def handle_popup(popup):
                        try:
                            print(f"[UNLOCKER] Blocked popup window at Chromium level.")
                            await popup.close()
                        except:
                            pass
                    page.on("popup", handle_popup)

                    # IMPORTANT: Force navigation to the target URL
                    print(f"[UNLOCKER] Navigating to target URL: {url}")
                    await page.goto(url, wait_until="domcontentloaded", timeout=45000)

                    print(f"[UNLOCKER] Page title: '{await page.title()}'")
      
                    # --- Find Matching Unlocker Config ---
                    matched_unlocker = {}
                    for unl in settings.UNLOCKERS:
                        patterns = unl.get("patterns", [])
                        if any(re.search(p, url) for p in patterns):
                            matched_unlocker = unl
                            break
                    
                    if matched_unlocker:
                        print(f"[UNLOCKER] Using config for: {matched_unlocker.get('name', 'Unknown')}")

                    # --- Configurable Mirror Traversal ---
                    mirror_selector = matched_unlocker.get("mirror_selector")
                    if mirror_selector:
                        print(f"[UNLOCKER] Looking for mirror link with selector: {mirror_selector}")
                        try:
                            delay = matched_unlocker.get("wait_delay", 0)
                            if delay:
                                await asyncio.sleep(delay)
                            mirror_locator = page.locator(mirror_selector)
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
                                print("[UNLOCKER] WARNING: No mirror link found.")
                        except Exception as me:
                            print(f"[UNLOCKER] Mirror traversal error: {me}")

                    # --- Configurable Button Traversal ---
                    wait_btn = matched_unlocker.get("wait_for")
                    click_btn = matched_unlocker.get("click")
                    if wait_btn and click_btn:
                        print(f"[UNLOCKER] Waiting for unlock button: {wait_btn}")
                        try:
                            btn = page.locator(wait_btn)
                            await btn.wait_for(state="visible", timeout=15000)
                            
                            print(f"[UNLOCKER] Clicking {click_btn}...")
                            await page.locator(click_btn).click()
                            
                            wait_res = matched_unlocker.get("wait_result")
                            if wait_res:
                                res_loc = page.locator(wait_res)
                                # Wait for attached because the input might be hidden in the DOM
                                await res_loc.wait_for(state="attached", timeout=15000)
                                await asyncio.sleep(2) # Stability
                                
                                attr = matched_unlocker.get("extract_attribute")
                                if attr:
                                    if attr == "text":
                                        final_url = await res_loc.inner_text()
                                    else:
                                        final_url = await res_loc.get_attribute(attr)
                                else:
                                    final_url = None

                                if final_url:
                                    print(f"[UNLOCKER] SUCCESS: Link found in input: {final_url}")
                                    final_links.append(final_url)
                                    await page.close()
                                    break
                        except Exception as ze:
                            print(f"[UNLOCKER] Button traversal error: {ze}")
                            raise ze

                    else:
                        # Wait for the validation button (Turnstile success) - Skips if configured
                        if matched_unlocker.get("skip_turnstile"):
                            print("[UNLOCKER] Config says skip Turnstile check.")
                            solved = True
                        else:
                            btn = page.locator("#subButton")
                            try:
                                print("[UNLOCKER] Waiting for Turnstile validation...")
                                await btn.wait_for(state="attached", timeout=15000)
                                await btn.wait_for(state="visible", timeout=15000)

                                # --- Multi-attempt strategy: Wait -> Reload -> Fallback Click ---
                                solved = False
                                for attempt_cf in range(1, 3):
                                    print(f"[UNLOCKER] Turnstile attempt {attempt_cf}/2...")
                                    attempt_start = time.time()
                                    attempt_timeout = 25 # seconds per attempt
                                    
                                    while time.time() - attempt_start < attempt_timeout:
                                        # 1. Detect the Turnstile Frame
                                        cf_frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"], iframe[title*="Cloudflare"]').first
                                        
                                        # 2. Check if already solved (Success checkmark or button enabled)
                                        is_success = await cf_frame.locator('#success:not([style*="display: none"])').is_visible()
                                        if is_success or await btn.is_enabled():
                                            print(f"[UNLOCKER] Turnstile solved on attempt {attempt_cf}!")
                                            solved = True
                                            break
                                        
                                        # 3. Fallback: Try a single click ONLY on the 2nd attempt after some waiting
                                        if attempt_cf == 2 and time.time() - attempt_start > 10:
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
                                    
                                    if attempt_cf == 1:
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
                                raise e

                        # --- Final extraction (Common for all flows) ---
                        print(f"[UNLOCKER] Reached final page: {page.url}")
                        
                        # Specific wait for final hoster links to load
                        wait_final = matched_unlocker.get("wait_for_final")
                        if wait_final:
                            print(f"[UNLOCKER] Waiting for final hoster links to load: {wait_final}")
                            try:
                                await page.wait_for_selector(wait_final, timeout=15000)
                                await asyncio.sleep(3) # Extra stability for dynamic elements
                            except Exception as e:
                                print(f"[UNLOCKER] Note: Timeout waiting for specific selectors ({e}). Proceeding with current content.")

                        content = await page.content()
                        total_extracted = 0
                        
                        # 1. Standard pattern matching
                        patterns_to_check = extra_patterns if extra_patterns else list(settings.DIRECT_SCAN_PATTERNS)
                        
                        for pattern in patterns_to_check:
                            print(f"[UNLOCKER] Checking pattern: {pattern}")
                            found = list(set(re.findall(pattern, content, re.IGNORECASE)))
                            if found:
                                print(f"[UNLOCKER] SUCCESS: {len(found)} link(s) extracted using pattern.")
                                final_links.extend(found)
                                total_extracted += len(found)

                        if total_extracted == 0:
                            print(f"[UNLOCKER] WARNING: No links extracted from {page.url}")
                            print(f"[UNLOCKER] Page Title: '{await page.title()}'")
                            raise ValueError("No links extracted from the final page")
                        
                        await page.close()
                        break
                        
                except Exception as e:
                    print(f"[UNLOCKER] Attempt {attempt} failed: {e}")
                    try:
                        if 'page' in locals() and page:
                            await page.close()
                    except:
                        pass
                    if attempt < max_attempts:
                        await asyncio.sleep(3)
                        
        return sorted(list(set(final_links)))
