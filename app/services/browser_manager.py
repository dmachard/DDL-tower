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

    async def ensure_browser(self, url: str = "about:blank", force: bool = False):
        """Ensures Chromium is running in Webtop with CDP enabled."""
        if not self.docker_client:
            print("[BROWSER-MGR] ERROR: No Docker client available.")
            return None

        try:
            container = self.docker_client.containers.get(self.container_name)
            
            # Check if both processes are running and port is responding
            if not force and self._is_browser_running(container):
                res = container.exec_run(f"curl -s http://127.0.0.1:{self.cdp_port}/json/version")
                if res.exit_code == 0:
                    return container
                print("[BROWSER-MGR] Browser port not responding. Restarting...")

            print(f"[BROWSER-MGR] {'Restarting' if force else 'Launching'} Chromium and socat in {self.container_name}...")
            
            # 1. Cleanup & Persistent IPv6 Priority
            container.exec_run("sh -c \"grep -q 'fd00::/8' /etc/gai.conf || echo 'precedence fd00::/8 50' >> /etc/gai.conf\"", user="root")
            container.exec_run("pkill -9 chromium", user="root")
            container.exec_run("pkill -9 socat", user="root")
            
            # Thorough cleanup of locks and service workers
            container.exec_run("sh -c 'rm -rf /config/.config/chromium/Singleton*'", user="root")
            # Aggressive cleanup of Service Workers and Cache across all profiles
            container.exec_run("sh -c \"find /config/.config/chromium -name 'Service Worker' -exec rm -rf {} +\"", user="root")
            container.exec_run("sh -c \"find /config/.config/chromium -name 'Cache' -exec rm -rf {} +\"", user="root")
            container.exec_run("sh -c \"find /config/.config/chromium -name 'Code Cache' -exec rm -rf {} +\"", user="root")
            container.exec_run("sh -c \"find /config/.config/chromium -name 'Script Guide' -exec rm -rf {} +\"", user="root")

            # 2. Launch Chromium on local port (internal only)
            # Added more flags to disable background activities and service workers
            stealth_flags = (
                "--disable-blink-features=AutomationControlled "
                "--disable-infobars "
                "--no-first-run "
                "--disable-gpu "
                "--disable-dev-shm-usage "
                "--disable-service-workers "
                "--disable-features=ServiceWorker,ServiceWorkerService,IsolateOrigins,site-per-process,SpeculativeServiceWorkerStartOnNavigation "
                "--disable-async-dns " # Force system DNS (to respect IPv6 priority)
                "--disable-notifications "
                "--disable-device-discovery-notifications "
                "--disable-background-networking "
                "--disable-background-timer-throttling "
                "--disable-backgrounding-occluded-windows "
                "--disable-breakpad "
                "--disable-client-side-phishing-detection "
                "--disable-component-update "
                "--disable-default-apps "
                "--disable-domain-reliability "
                "--disable-extensions "
                "--disable-hang-monitor "
                "--disable-ipc-flooding-protection "
                "--disable-popup-blocking "
                "--disable-prompt-on-repost "
                "--disable-renderer-backgrounding "
                "--disable-sync "
            )
            profile_path = "/config/.config/chromium" 

            container.exec_run(
                cmd=(
                    f"env DISPLAY=:1 chromium --no-sandbox {stealth_flags} "
                    f"--remote-debugging-port={self.local_cdp_port} "
                    f"--remote-allow-origins=* "
                    f"--user-data-dir={profile_path} about:blank"
                ),
                detach=True,
                user="root"
            )

            # 3. Bridge the CDP port with socat (to allow external connections)
            container.exec_run(
                cmd=f"/usr/bin/socat TCP-LISTEN:{self.cdp_port},fork,reuseaddr TCP:127.0.0.1:{self.local_cdp_port}",
                detach=True,
                user="root"
            )

            # Wait for startup and check readiness (up to 15s)
            for i in range(15):
                await asyncio.sleep(1)
                # Check internal port first
                res = container.exec_run(f"curl -s http://127.0.0.1:{self.local_cdp_port}/json/version")
                if res.exit_code == 0:
                    # Then check external bridged port
                    res_ext = container.exec_run(f"curl -s http://127.0.0.1:{self.cdp_port}/json/version")
                    if res_ext.exit_code == 0:
                        return container
            
            print("[BROWSER-MGR] WARNING: Browser started but port not responding after 15s")
            return container

        except Exception as e:
            print(f"[BROWSER-MGR] Error ensuring browser: {e}")
            return None

    async def restart_browser(self):
        """Forces a complete restart of the browser."""
        return await self.ensure_browser(force=True)

    async def get_browser(self, playwright: Playwright, url: str = "about:blank") -> Optional[Browser]:
        """
        Connects to the remote browser, starting it if necessary.
        Returns None if remote connection is required but fails.
        """
        await self.ensure_browser(url)
        
        ip = await self.get_container_ip()
        cdp_url = f"http://{ip}:{self.cdp_port}"
        
        # print(f"[BROWSER-MGR] Connecting to {cdp_url}...")
        try:
            return await playwright.chromium.connect_over_cdp(cdp_url, timeout=20000)
        except Exception as e:
            print(f"[BROWSER-MGR] CDP Connection failed: {e}. Attempting recovery restart...")
            # If it fails, maybe the browser or driver is in a bad state (zombie/crashed)
            # We force a restart
            await self.restart_browser()
            
            try:
                # Second attempt after restart
                return await playwright.chromium.connect_over_cdp(cdp_url, timeout=20000)
            except Exception as e2:
                print("\n" + "!" * 60)
                print("!!! FATAL BROWSER ERROR !!!")
                print(f"!!! Could not connect to Webtop at {cdp_url} even after forced restart")
                print(f"!!! Error: {e2}")
                print("!!! Scraping blocked to avoid headless execution.")
                print("!" * 60 + "\n")
                return None

browser_manager = BrowserManager()
