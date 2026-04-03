import math
import PTN # NEW: For cleaning override_title
from datetime import datetime, timezone
from typing import List
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import DownloadLink
from app.core.hoster import Hoster
from app.core.utils import format_size # Import generic utility

class LinkManager:
    def __init__(self):
        self.hoster = Hoster()

    async def check_links(self, session: AsyncSession, raw_links: List[str], source_url: str, source_name: str, override_filename: str = None) -> List[DownloadLink]:
        """
        Manages ONLY physical links: 
        AllDebrid verification AND database insertion.
        If override_filename is provided, it's used as the base filename (useful for multi-part).
        """
        if not raw_links: return

        # 1. Filter links already present in the DB
        q_links = await session.execute(
            select(DownloadLink.url).where(
                DownloadLink.url.in_(raw_links)
            )
        )
        known_urls = [r[0] for r in q_links.all()]
        new_links = [l for l in raw_links if l not in known_urls]
        
        if not new_links:
            print(f"[LINK] No new links for {source_name}.")
            return

        print(f"[LINK] Verifying {len(new_links)} new links via hoster...")
        hv_results = await self.hoster.check_links(new_links)
        
        added_links = []
        
        for link in new_links:
            info = hv_results.get(link, {"status": "unknown"})
            # Source of truth for filename: override_filename if present, else what hoster found
            filename = override_filename if override_filename else info.get('filename')
            status = info.get('status', 'dead')
            
            new_db_link = DownloadLink(
                url=link,
                hoster=info.get('host', 'unknown'),
                status=status,
                filename=filename,
                size=format_size(info.get('size', 0)),
                size_bytes=info.get('size', 0),
                last_checked=datetime.now(timezone.utc),
                source_name=source_name,
                source_url=source_url
            )
            session.add(new_db_link)
            added_links.append(new_db_link)
            print(f"[LINK] Added link: {filename or link}")
        
        return added_links

