from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.debrid.alldebrid import AllDebridClient
from app.debrid.realdebrid import RealDebridClient
from app.debrid.bestdebrid import BestDebridClient

class DebridService:
    def __init__(self):
        self.alldebrid = AllDebridClient()
        self.realdebrid = RealDebridClient()
        self.bestdebrid = BestDebridClient()

    def get_enabled_clients(self):
        """Returns a list of all clients that have an API key configured."""
        clients = []
        if settings.ALLDEBRID_ENABLED:
            clients.append(self.alldebrid)
        if settings.REALDEBRID_ENABLED:
            clients.append(self.realdebrid)
        if settings.BESTDEBRID_ENABLED:
            clients.append(self.bestdebrid)
        return clients

    async def check_links(self, links: List[str]) -> Dict[str, Any]:
        """Check links using the primary client."""
        clients = self.get_enabled_clients()
        if not clients: return {}
        return await clients[0].check_links(links)

    async def unlock_link(self, link: str) -> Dict[str, Any]:
        """
        Attempts to unlock a link using enabled clients.
        Falls back to the next client if the first one fails.
        """
        import asyncio

        clients = self.get_enabled_clients()
        if not clients:
            return {"status": "failed", "error": "No debrid service configured"}

        last_res = {"status": "failed", "error": "Unknown error"}
        for client in clients:
            max_retries = 3
            for attempt in range(1, max_retries + 1):
                res = await client.unlock_link(link)
                if res.get("status") == "success":
                    return res
                
                err_msg = ""
                error_val = res.get("error", "")
                if isinstance(error_val, dict):
                    err_msg = error_val.get("message") or error_val.get("code") or str(error_val)
                else:
                    err_msg = str(error_val)
                
                # Check for temporary/hoster errors that justify a retry
                is_temporary = any(term in err_msg.lower() for term in [
                    "not available on the file hoster",
                    "host_unreachable",
                    "hoster_unavailable",
                    "link_host_no_link",
                    "bad_link"
                ])
                
                if is_temporary and attempt < max_retries:
                    delay = attempt * 3 # 3s, 6s delay
                    print(f"[DEBRID] {client.__class__.__name__} failed to unlock {link}: '{err_msg}'. Retrying in {delay}s (Attempt {attempt}/{max_retries})...")
                    await asyncio.sleep(delay)
                else:
                    last_res = res
                    print(f"[DEBRID] {client.__class__.__name__} failed to unlock: {err_msg}. Trying next...")
                    break

        return last_res

# Global instance
debrid_service = DebridService()
