import math
from datetime import datetime, timezone
from typing import List
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import DownloadLink
from app.services.alldebrid import AllDebridClient

class LinkManager:
    def __init__(self):
        self.ad_client = AllDebridClient()

    async def check_links(self, session: AsyncSession, raw_links: List[str], source_url: str, source_name: str):
        """
        Manages ONLY physical links: 
        AllDebrid verification AND database insertion.
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

        print(f"[LINK] Verifying {len(new_links)} new links via AllDebrid...")
        ad_results = await self.ad_client.check_links(new_links)

        for link, info in ad_results.items():
            filename = info.get('filename')
            status = info.get('status', 'dead')
            
            new_link = DownloadLink(
                url=link,
                hoster=info.get('host', 'unknown'),
                status=status,
                filename=filename,
                size=self._format_size(info.get('size', 0)),
                last_checked=datetime.now(timezone.utc),
                source_name=source_name
            )
            session.add(new_link)
            print(f"[LINK] Added link to DB: {filename}")

    def _format_size(self, size_bytes: int) -> str:
        if size_bytes == 0: return "0B"
        import math
        size_name = ("B", "KB", "MB", "GB", "TB")
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_name[i]}"
