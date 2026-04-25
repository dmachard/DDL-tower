from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.services.alldebrid import AllDebridClient
from app.services.realdebrid import RealDebridClient
from app.services.bestdebrid import BestDebridClient

class DebridService:
    def __init__(self):
        self.alldebrid = AllDebridClient()
        self.realdebrid = RealDebridClient()
        self.bestdebrid = BestDebridClient()

    def get_client(self):
        """
        Returns the first available client that has an API key configured.
        Prioritizes AllDebrid if both are present.
        """
        if settings.ALLDEBRID_API_KEY and settings.ALLDEBRID_API_KEY != "[YOUR_KEY]":
            return self.alldebrid
        if settings.REALDEBRID_API_KEY and settings.REALDEBRID_API_KEY != "[YOUR_KEY]":
            return self.realdebrid
        if settings.BESTDEBRID_API_KEY and settings.BESTDEBRID_API_KEY != "[YOUR_KEY]":
            return self.bestdebrid
        
        # Fallback to AllDebrid (it will log a warning about missing key)
        return self.alldebrid

    async def check_links(self, links: List[str]) -> Dict[str, Any]:
        return await self.get_client().check_links(links)

    async def unlock_link(self, link: str) -> Dict[str, Any]:
        return await self.get_client().unlock_link(link)

# Global instance
debrid_service = DebridService()
