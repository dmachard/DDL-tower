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
        clients = self.get_enabled_clients()
        if not clients:
            return {"status": "failed", "error": "No debrid service configured"}

        last_res = {"status": "failed", "error": "Unknown error"}
        for client in clients:
            res = await client.unlock_link(link)
            if res.get("status") == "success":
                return res
            
            # If it's a specific error like infringing_file, we might want to log it
            # and try the next one anyway, as another debrid might have it cached.
            last_res = res
            print(f"[DEBRID] {client.__class__.__name__} failed to unlock: {res.get('error')}. Trying next...")

        return last_res

# Global instance
debrid_service = DebridService()
