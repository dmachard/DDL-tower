import asyncio
import docker
import socket
import re
from typing import Optional
from playwright.async_api import Playwright, Browser
from app.core.config import settings

class BrowserManager:
    """
    Centralized service to manage the lifecycle of the Chromium browser 
    inside the Webtop container.
    """
    def __init__(self):
        self.container_name = settings.WEBTOP_CONTAINER_NAME
        self.cdp_port = 9222
        self.local_cdp_port = 9223
        self._diagnostics_done = False
        
        # Try to extract container name from BROWSER_URL if provided
        if settings.BROWSER_URL:
            # e.g. http://ddltower-browser:9222 -> ddltower-browser
            match = re.search(r'https?://([^:/]+)', settings.BROWSER_URL)
            if match:
                self.container_name = match.group(1)
                
        try:
            self.docker_client = docker.from_env()
        except Exception as e:
            print(f"[BROWSER-MGR] ERROR: Could not connect to Docker: {e}")
            self.docker_client = None

    async def run_diagnostics(self):
        """Performs a full health check of the browser infrastructure."""
        if self._diagnostics_done: return
        
        print("\n" + "="*60)
        print(" BROWSER INFRASTRUCTURE DIAGNOSTICS")
        print("="*60)
        
        # 1. Docker Socket
        if not self.docker_client:
            print("[-] Docker Socket: FAILED (Permission denied or not mounted)")
        else:
            print("[+] Docker Socket: OK")
            
            # 2. Webtop Container
            try:
                container = self.docker_client.containers.get(self.container_name)
                print(f"[+] Webtop Container ({self.container_name}): FOUND")
                
                # 3. Socat check
                res = container.exec_run("which socat")
                if res.exit_code == 0:
                    print("[+] Socat tool: INSTALLED")
                else:
                    print("[-] Socat tool: MISSING (Please run: docker exec ddltower-browser apt-get install -y socat)")
                
                # 4. Chrome check
                res = container.exec_run("which chromium")
                if res.exit_code == 0:
                    print("[+] Chromium browser: FOUND")
                else:
                    print("[-] Chromium browser: MISSING inside container")
                    
            except Exception as e:
                print(f"[-] Webtop Container ({self.container_name}): NOT ACCESSIBLE ({e})")
        
        print("="*60 + "\n")
        self._diagnostics_done = True

    async def get_container_ip(self) -> str:
        try:
            return socket.gethostbyname(self.container_name)
        except socket.gaierror:
            return "127.0.0.1"

    def _is_browser_running(self, container) -> bool:
        """Checks if chromium and socat processes are active."""
        try:
            # Check for actual chromium process
            res_chrome = container.exec_run("pgrep -f chromium")
            # Check for socat process
            res_socat = container.exec_run("pgrep socat")
            
            return res_chrome.exit_code == 0 and res_socat.exit_code == 0
        except Exception as e:
            print(f"[BROWSER-MGR] Error during running check: {e}")
            return False

    async def ensure_browser(self, url: str = "about:blank"):
        """Ensures Chromium is running in Webtop with CDP enabled."""
        if not self.docker_client:
            print("[BROWSER-MGR] ERROR: No Docker client available.")
            return None

        try:
            container = self.docker_client.containers.get(self.container_name)
            
            if self._is_browser_running(container):
                print(f"[BROWSER-MGR] Browser is already running and ready in {self.container_name}")
                return container

            print(f"[BROWSER-MGR] Browser not started. Launching Chromium and socat in {self.container_name}...")
            
            # 1. Cleanup just in case
            container.exec_run("pkill chromium", user="root")
            container.exec_run("pkill socat", user="root")

            # 2. Launch Chromium with stealth flags and real user profile to share cookies/sessions
            stealth_flags = (
                "--disable-blink-features=AutomationControlled "
                "--disable-infobars "
                "--no-first-run "
            )
            # Standard profile path for Linuxserver Webtop
            profile_path = "/config/.config/chromium" 

            container.exec_run(
                cmd=f"env DISPLAY=:1 chromium --no-sandbox {stealth_flags} --remote-debugging-port={self.local_cdp_port} --remote-allow-origins=* --user-data-dir={profile_path} '{url}'",
                detach=True,
                user="abc"
            )

            # 3. Bridge the CDP port with socat
            container.exec_run(
                cmd=f"socat TCP-LISTEN:{self.cdp_port},fork,reuseaddr TCP:127.0.0.1:{self.local_cdp_port}",
                detach=True,
                user="root"
            )

            # Wait for startup (give it enough time to open the port)
            await asyncio.sleep(5)
            return container

        except Exception as e:
            print(f"[BROWSER-MGR] Error ensuring browser: {e}")
            return None

    async def get_browser(self, playwright: Playwright, url: str = "about:blank") -> Optional[Browser]:
        """
        Connects to the remote browser, starting it if necessary.
        Returns None if remote connection is required but fails.
        """
        await self.ensure_browser(url)
        
        ip = await self.get_container_ip()
        cdp_url = f"http://{ip}:{self.cdp_port}"
        
        print(f"[BROWSER-MGR] Connecting to {cdp_url}...")
        try:
            return await playwright.chromium.connect_over_cdp(cdp_url, timeout=15000)
        except Exception as e:
            print("\n" + "!" * 60)
            print("!!! FATAL BROWSER ERROR !!!")
            print(f"!!! Could not connect to Webtop at {cdp_url}")
            print(f"!!! Error: {e}")
            print("!!! Scraping blocked to avoid headless execution.")
            print("!" * 60 + "\n")
            return None

browser_manager = BrowserManager()
