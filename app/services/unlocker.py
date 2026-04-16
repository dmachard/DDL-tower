import asyncio
import re
import docker
import socket
import time
from typing import List
from playwright.async_api import async_playwright
from app.core.config import settings

class LinkUnlocker:
    """
    Advanced Link Unlocker that uses the Webtop container via Docker SDK
    to bypass Cloudflare/Turnstile.
    """
    def __init__(self, container_name=None, cdp_port=9222, local_cdp_port=9223):
        self.container_name = container_name or settings.WEBTOP_CONTAINER_NAME
        self.cdp_port = cdp_port
        self.local_cdp_port = local_cdp_port
        try:
            self.client = docker.from_env()
        except Exception as e:
            print(f"[UNLOCKER] Could not connect to Docker: {e}")
            self.client = None

    async def get_container_ip(self):
        try:
            return socket.gethostbyname(self.container_name)
        except socket.gaierror:
            return "127.0.0.1"

    def setup_container_env(self, url):
        """Prepares the Webtop container for extraction."""
        if not self.client:
            print("[UNLOCKER] ERROR: No Docker client available.")
            return None
            
        try:
            container = self.client.containers.get(self.container_name)
        except Exception as e:
            print(f"[UNLOCKER] ERROR: Container '{self.container_name}' not found or unreachable: {e}")
            return None

        # 1. Ensure socat is present
        # Check if socat is already installed (fast)
        try:
            res = container.exec_run("which socat")
            if res.exit_code != 0:
                print(f"[UNLOCKER] socat not found in {self.container_name}. Attempting quick install...")
                # Try install without update first (faster if cache exists)
                res_inst = container.exec_run("apt-get install -y socat", user="root")
                if res_inst.exit_code != 0:
                    print("[UNLOCKER] Quick install failed. Running apt-get update (may be slow)...")
                    container.exec_run("apt-get update", user="root")
                    container.exec_run("apt-get install -y socat", user="root")
            else:
                print(f"[UNLOCKER] socat is ready in {self.container_name}")
        except Exception as e:
            print(f"[UNLOCKER] Warning: Failed to verify/install socat: {e}")

        # 2. Cleanup previous runs
        container.exec_run("pkill chromium", user="root")
        container.exec_run("pkill socat", user="root")

        # 3. Launch Browser inside Webtop container
        print(f"[UNLOCKER] Launching Chromium in {self.container_name} for {url}")
        container.exec_run(
            cmd=f"env DISPLAY=:1 chromium --no-sandbox --remote-debugging-port={self.local_cdp_port} --remote-allow-origins=* --user-data-dir=/tmp/automation-profile '{url}'",
            detach=True,
            user="abc"
        )

        # 4. Bridge the CDP port to the container's network interface
        container.exec_run(
            cmd=f"socat TCP-LISTEN:{self.cdp_port},fork,reuseaddr TCP:127.0.0.1:{self.local_cdp_port}",
            detach=True,
            user="root"
        )
        return container

    async def unlock(self, url: str) -> List[str]:
        """Unlocks a dl-protect.link and returns the final file hoster links."""
        print(f"[UNLOCKER] Starting unlock process for: {url}")
        
        container = self.setup_container_env(url)
        if not container:
            return []

        # Give the container some time to start Chromium and socat
        await asyncio.sleep(4)
        
        ip = await self.get_container_ip()
        cdp_url = f"http://{ip}:{self.cdp_port}"
        
        final_links = []
        async with async_playwright() as p:
            browser = None
            # Retry connection loop (3 attempts)
            for attempt in range(1, 4):
                try:
                    print(f"[UNLOCKER] Connecting to remote browser (Attempt {attempt}/3)...")
                    browser = await p.chromium.connect_over_cdp(cdp_url, timeout=15000)
                    break 
                except Exception as e:
                    if attempt == 3:
                        print(f"[UNLOCKER] Final connection failure: {e}")
                        return []
                    await asyncio.sleep(3)

            try:
                # Use the existing tab or create a new one
                context = browser.contexts[0]
                page = context.pages[0] if context.pages else await context.new_page()
                
                print(f"[UNLOCKER] Page title: '{await page.title()}'")
                
                # Wait for the validation button (Turnstile success)
                btn = page.locator("#subButton")
                try:
                    print("[UNLOCKER] Waiting for Turnstile validation...")
                    await btn.wait_for(state="attached", timeout=60000)

                    print("[UNLOCKER] Waiting for Turnstile validation...")
                    await btn.wait_for(state="visible", timeout=60000)

                    # --- Improved: Check for interactive Turnstile checkbox ---
                    print("[UNLOCKER] Monitoring Turnstile interaction...")
                    start_time = time.time()
                    max_wait = 45 
                    
                    while time.time() - start_time < max_wait:
                        try:
                            # 1. Detect the Turnstile Frame
                            cf_frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"], iframe[title*="Cloudflare"]').first
                            
                            # 2. Check if already solved (Success checkmark)
                            if await cf_frame.locator('#success').is_visible():
                                print("[UNLOCKER] Turnstile Success detected.")
                                break

                            # 3. Try to find and click the checkbox
                            selectors = ['input[type="checkbox"]', '.ctp-checkbox-label', '.mark', '#challenge-stage']
                            for selector in selectors:
                                target = cf_frame.locator(selector).first
                                if await target.count() > 0 and await target.is_visible():
                                    print(f"[UNLOCKER] Turnstile checkbox/challenge found ({selector}). Clicking...")
                                    # hover() is vital: it handles iframe offsets correctly!
                                    await target.hover(timeout=5000)
                                    await asyncio.sleep(0.5)
                                    await target.click(timeout=5000)
                                    print("[UNLOCKER] Click performed.")
                                    await asyncio.sleep(3) # Give it time to register
                                    break
                        except Exception as e:
                            # Frame might not be ready or detached during check
                            pass
                        
                        # 4. Check if the 'Continuer' button is now enabled (solved)
                        if await btn.is_enabled():
                            print("[UNLOCKER] Turnstile solved (subButton is enabled).")
                            break
                            
                        await asyncio.sleep(2)

                    print("[UNLOCKER] Clicking 'Continuer' button (auto-waiting for it to be enabled)...")
                    async with page.expect_navigation(timeout=60000):
                        # click() will wait for the button to be enabled (Turnstile solved)
                        await btn.click(timeout=60000)
                    
                    print("[UNLOCKER] Turnstile passed!")
                    
                    print(f"[UNLOCKER] Reached final page: {page.url}")

                    # Extract final hoster links using configured global patterns
                    content = await page.content()
                    
                    for pattern in settings.DIRECT_SCAN_PATTERNS:
                        found = list(set(re.findall(pattern, content, re.IGNORECASE)))
                        if found:
                            print(f"[UNLOCKER] {len(found)} link(s) extracted from final page.")
                            final_links.extend(found)

                except Exception as e:
                    print(f"[UNLOCKER] Page error or timeout: {e}")
                
                if browser:
                    await browser.close()
                
                # Cleanup container processes
                container.exec_run("pkill chromium", user="root")
                container.exec_run("pkill socat", user="root")
            except Exception as e:
                print(f"[UNLOCKER] Error during extraction: {e}")
                if browser: await browser.close()
                container.exec_run("pkill chromium", user="root")
                container.exec_run("pkill socat", user="root")
                
        return sorted(list(set(final_links)))
