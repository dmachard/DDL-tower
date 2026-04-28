import math
import PTN # NEW: For cleaning override_title
from datetime import datetime, timezone
from typing import List
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import DownloadLink
from app.core.hoster import Hoster
from app.core.utils import format_size

class LinkManager:
    def __init__(self):
        self.hoster = Hoster()

    async def check_links(self, session: AsyncSession, raw_links: List[str], source_url: str, source_name: str, 
                          override_filename: str = None, override_title: str = None, override_year: int = None, 
                          tags: List[str] = None) -> List[DownloadLink]:
        """
        Manages link verification and database insertion with duplicate prevention.
        """
        if not raw_links: return []
        
        # 1. Clean and deduplicate incoming list
        raw_links = list(set([l.strip() for l in raw_links if l]))

        # 2. Identify links that are truly new (not in DB AND not in current session)
        # We flush current changes to make sure the SELECT can see them if they were just added
        try:
            await session.flush()
        except:
            await session.rollback()
            raise

        q_links = await session.execute(
            select(DownloadLink.url).where(DownloadLink.url.in_(raw_links))
        )
        known_urls = {r[0] for r in q_links.all()}
        
        # Also check links currently pending in the session to avoid double-adding in same batch
        for obj in session.new:
            if isinstance(obj, DownloadLink):
                known_urls.add(obj.url)

        new_links = [l for l in raw_links if l not in known_urls]
        
        if not new_links:
            print(f"[LINK] No new links for {source_name} in this batch.")
            return []

        print(f"[LINK] Verifying {len(new_links)} new links via hoster...")
        hv_results = await self.hoster.check_links(new_links)
        
        added_links = []
        import sqlalchemy.exc
        
        for link in new_links:
            info = hv_results.get(link, {"status": "unknown"})
            h_filename = info.get('filename')
            status = info.get('status', 'dead')
            
            final_filename = override_filename if override_filename else h_filename

            try:
                # Use a nested transaction (savepoint) so we can gracefully recover from IntegrityError
                async with session.begin_nested():
                    # Double-check if the link was added by another task while we were awaiting hoster
                    q = await session.execute(select(DownloadLink).where(DownloadLink.url == link))
                    existing = q.scalar_one_or_none()
                    
                    if existing:
                        existing.status = status
                        existing.filename = final_filename
                        # Only update titles if we have a new override, or if they were empty
                        if override_title:
                            existing.title = override_title
                            existing.raw_title = override_title
                        elif not existing.raw_title:
                            existing.raw_title = final_filename
                        
                        existing.year = override_year
                        existing.size = format_size(info.get('size', 0))
                        existing.size_bytes = info.get('size', 0)
                        existing.last_checked = datetime.now(timezone.utc)
                        existing.source_name = source_name
                        existing.source_url = source_url
                        existing.language = ", ".join(tags) if tags else None
                        added_links.append(existing)
                    else:
                        new_db_link = DownloadLink(
                            url=link,
                            hoster=info.get('host', 'unknown'),
                            status=status,
                            filename=final_filename,
                            title=override_title, # Can be None, will be filled by Categorizer
                            raw_title=override_title or final_filename, # Use filename as raw fallback for tooltips
                            year=override_year,
                            size=format_size(info.get('size', 0)),
                            size_bytes=info.get('size', 0),
                            last_checked=datetime.now(timezone.utc),
                            source_name=source_name,
                            source_url=source_url,
                            language=", ".join(tags) if tags else None
                        )
                        session.add(new_db_link)
                        added_links.append(new_db_link)
                    
                    # Flush immediately so any IntegrityError is raised inside the savepoint block
                    await session.flush()
                    print(f"[LINK] Added/Updated link: {final_filename or link}")
            except sqlalchemy.exc.IntegrityError:
                print(f"[LINK] Race condition inserting {link}, skipped.")
        
        # Final flush for this batch
        await session.flush()
        return added_links
