import asyncio
import re
import time
from typing import List
from playwright.async_api import async_playwright
from app.core.config import settings
from app.core.template_matcher import find_template, save_debug_match

# Path to the reference button image used for template matching.
# Single template shared across all unlocker configs.
TURNSTILE_BUTTON_TEMPLATE = "data/templates/button.png"
TEMPLATE_MATCH_MIN_CONFIDENCE = 0.55


class LinkUnlocker:
    """
    Advanced Link Unlocker that uses the Webtop container 
    to bypass Cloudflare/Turnstile.
    """
    def __init__(self):
        pass

    async def _click_via_template_matching(
        self,
        page,
        template_path: str = TURNSTILE_BUTTON_TEMPLATE,
        min_confidence: float = TEMPLATE_MATCH_MIN_CONFIDENCE,
        max_wait_seconds: int = 25,
        poll_interval: float = 2.0,
        bypass_selectors: List[str] = None,
    ) -> bool:
        """
        Poll the page with screenshots, locate `template_path` via template
        matching, and click its center once found with sufficient confidence.
        If a bypass selector is visible, exits early returning True.

        Returns True if a click or auto-bypass was performed, False if the template was
        never found above `min_confidence` within `max_wait_seconds`.
        """
        start = time.time()
        last_match = None
        last_screenshot_bytes = None

        while time.time() - start < max_wait_seconds:
            if bypass_selectors:
                for selector in bypass_selectors:
                    try:
                        loc = page.locator(selector).first
                        if await loc.is_visible() and await loc.is_enabled():
                            print(
                                f"[UNLOCKER] Bypass selector '{selector}' detected and enabled. "
                                f"Turnstile bypassed automatically."
                            )
                            return True
                    except Exception:
                        pass

            screenshot_bytes = await page.screenshot()
            last_screenshot_bytes = screenshot_bytes
            match = find_template(screenshot_bytes, template_path, min_confidence)
            last_match = match

            print(
                f"[UNLOCKER] Template match confidence: {match.confidence:.3f} "
                f"(threshold {min_confidence})"
            )

            if match.found:
                cx, cy = match.center
                print(f"[UNLOCKER] Template found, clicking at ({cx}, {cy})...")
                try:
                    save_debug_match(
                        screenshot_bytes, match, "data/error_dumps/template_success.png"
                    )
                except Exception as dump_err:
                    print(f"[UNLOCKER] Failed to save success template debug dump: {dump_err}")
                await page.mouse.click(cx, cy)
                return True

            await asyncio.sleep(poll_interval)

        # Save a debug dump of the last attempt so the miss can be diagnosed.
        if last_match is not None and last_screenshot_bytes is not None:
            try:
                save_debug_match(
                    last_screenshot_bytes, last_match, "data/error_dumps/template_miss.png"
                )
            except Exception as dump_err:
                print(f"[UNLOCKER] Failed to save template debug dump: {dump_err}")

        print("[UNLOCKER] WARNING: Template not found within timeout.")
        return False

    async def unlock(self, url: str, extra_patterns: List[str] = None) -> List[str]:
        """Unlocks a dl-protect.link and returns the final file hoster links."""
        print(f"[UNLOCKER] Starting unlock process for: {url}")
        
        from app.services.browser_manager import browser_manager
        
        final_links = []
        last_exception = Exception("Unknown unlock error")
        async with async_playwright() as p:
            browser = None
            max_attempts = 3
            for attempt in range(1, max_attempts + 1):
                if attempt > 1:
                    print(f"[UNLOCKER] Retry attempt {attempt}/{max_attempts} for: {url}")
                
                try:
                    # Reconnect if browser not set or connection lost
                    if not browser or not browser.is_connected():
                        browser = await browser_manager.get_browser(p, url=url)
                    if not browser:
                        raise Exception("Webtop browser container unavailable")
                    
                    # Always use a NEW page for isolation
                    page = await browser.new_page()
                    
                    # --- Auto-close all popups at Chromium level ---
                    async def handle_popup(popup):
                        try:
                            print(f"[UNLOCKER] Blocked popup window at Chromium level.")
                            await popup.close()
                        except Exception:
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
                            # Wait for the first mirror element to load dynamically
                            try:
                                await mirror_locator.first.wait_for(state="attached", timeout=10000)
                            except Exception:
                                print("[UNLOCKER] Mirror selector not found after wait timeout.")
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

                    # --- Step 1: Turnstile check (if not skipped) ---
                    wait_btn = matched_unlocker.get("wait_for")
                    click_btn = matched_unlocker.get("click")
                    
                    if not matched_unlocker.get("skip_turnstile"):
                        already_unlocked = False
                        wait_final = matched_unlocker.get("wait_for_final")
                        
                        bypass_selectors = []
                        if wait_final:
                            bypass_selectors.append(wait_final)
                        if wait_btn:
                            bypass_selectors.append(wait_btn)

                        if bypass_selectors:
                            try:
                                print(f"[UNLOCKER] Checking if final page/links or action button are already visible (waiting up to 5s)...")
                                start_wait = time.time()
                                while time.time() - start_wait < 5.0:
                                    found_bypass = False
                                    for selector in bypass_selectors:
                                        try:
                                            loc = page.locator(selector).first
                                            if await loc.is_visible() and await loc.is_enabled():
                                                print(f"[UNLOCKER] Detected '{selector}' is visible and enabled. Skipping Turnstile check.")
                                                already_unlocked = True
                                                found_bypass = True
                                                break
                                        except Exception:
                                            pass
                                    if found_bypass:
                                        break
                                    await asyncio.sleep(0.5)
                            except Exception:
                                pass
                        
                        if already_unlocked:
                            print("[UNLOCKER] Final links already visible. Skipping Turnstile check.")
                        else:
                            try:
                                print("[UNLOCKER] Locating Turnstile/Continuer button via template matching...")
                                solved = False
                                # Use shorter wait if a fallback button traversal is configured
                                max_wait = 10 if wait_btn else 25
                                
                                template_file = matched_unlocker.get("turnstile_template") or TURNSTILE_BUTTON_TEMPLATE
                                clicked = await self._click_via_template_matching(
                                    page, 
                                    template_path=template_file, 
                                    max_wait_seconds=max_wait,
                                    bypass_selectors=bypass_selectors
                                )
                                if clicked:
                                    await asyncio.sleep(3)
                                    # Wait for the navigation triggered by the click to settle
                                    try:
                                        await page.wait_for_load_state("domcontentloaded", timeout=15000)
                                    except Exception as nav_err:
                                        print(f"[UNLOCKER] Post-click navigation wait skipped: {nav_err}")
                                    print("[UNLOCKER] Turnstile passed!")
                                    solved = True
                                
                                if not solved:
                                    if wait_btn:
                                        print("[UNLOCKER] Turnstile not matched (optional fallback). Proceeding to button traversal...")
                                    else:
                                        raise ValueError(
                                            "Template matching failed to locate the Turnstile/Continuer button"
                                        )
                            except Exception as e:
                                if not wait_btn:
                                    print(f"[UNLOCKER] Turnstile step failed: {e}")
                                    raise e
                                else:
                                    print(f"[UNLOCKER] Turnstile step warning (non-critical fallback): {e}")

                    # --- Step 2: Configurable Button Traversal ---
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

                    # --- Final extraction (Common for all flows) ---
                    print(f"[UNLOCKER] Reached final page: {page.url}")
                    
                    # Specific wait for final hoster links to load
                    wait_final = matched_unlocker.get("wait_for_final")
                    wait_final_error = None
                    if wait_final:
                        print(f"[UNLOCKER] Waiting for final hoster links to load: {wait_final}")
                        try:
                            await page.wait_for_selector(wait_final, timeout=15000)
                            await asyncio.sleep(3) # Extra stability for dynamic elements
                        except Exception as e:
                            wait_final_error = e
                            print(f"[UNLOCKER] Note: Timeout waiting for specific selectors ({e}). Proceeding with current content.")

                    content = await page.content()
                    total_extracted = 0
                    
                    # 1. Standard pattern matching
                    patterns_to_check = extra_patterns if extra_patterns else list(settings.DIRECT_SCAN_PATTERNS)
                    
                    for pattern in patterns_to_check:
                        print(f"[UNLOCKER] Checking pattern: {pattern}")
                        # Extract the first capture group if the pattern contains capturing groups,
                        # otherwise default to the entire match.
                        matches = (m.group(1) if m.groups() else m.group(0) for m in re.finditer(pattern, content, re.IGNORECASE))
                        found = list(set(val for val in matches if val))
                        if found:
                            print(f"[UNLOCKER] SUCCESS: {len(found)} link(s) extracted using pattern.")
                            final_links.extend(found)
                            total_extracted += len(found)

                    if total_extracted == 0:
                        print(f"[UNLOCKER] WARNING: No links extracted from {page.url}")
                        print(f"[UNLOCKER] Page Title: '{await page.title()}'")
                        if wait_final_error:
                            raise ValueError(f"Timeout waiting for selector '{wait_final}' and no links extracted")
                        else:
                            raise ValueError("No links extracted from the final page")
                    
                    await page.close()
                    break
                        
                except Exception as e:
                    print(f"[UNLOCKER] Attempt {attempt} failed: {e}")
                    last_exception = e
                    if attempt == max_attempts:
                        try:
                            if 'page' in locals() and page:
                                from app.core.utils import save_error_dump
                                screenshot_path, html_path = await save_error_dump(url, page)
                                last_exception.screenshot_path = screenshot_path
                                last_exception.html_path = html_path
                        except Exception as dump_err:
                            print(f"[UNLOCKER] Failed to save error dump: {dump_err}")
                    try:
                        if 'page' in locals() and page:
                            await page.close()
                    except Exception:
                        pass
                    if attempt < max_attempts:
                        await asyncio.sleep(3)
                        
        if not final_links:
            raise last_exception
            
        return sorted(list(set(final_links)))