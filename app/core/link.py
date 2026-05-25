import math
import re
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

    def _get_best_raw_title(self, override_title: str, filename: str, url: str) -> str:
        """
        Determines the best string for the tooltip (raw_title).
        Prioritizes override_title (RSS) if filename is technical (.rar) or less descriptive.
        """
        if not override_title or override_title in ["Untitled", "None"]:
            return filename or override_title or url
        
        if not filename:
            return override_title
            
        # 1. If filename is clearly unhelpful (archive, part), use override_title
        bad_exts = ['.rar', '.zip', '.7z', '.tar', '.001', '.002']
        if any(filename.lower().endswith(ext) for ext in bad_exts) or '.part' in filename.lower():
            return override_title
            
        # 2. If override_title looks like a full release name (has resolution/year) 
        # and filename does not, use override_title
        tags_pattern = r'\b(720p|1080p|2160p|4k|bluray|webrip|web-dl|h26[45]|x26[45]|\b(19|20)\d{2}\b)\b'
        has_tags_override = bool(re.search(tags_pattern, override_title, re.I))
        has_tags_filename = bool(re.search(tags_pattern, filename, re.I))
        
        if has_tags_override and not has_tags_filename:
            return override_title
            
        # 3. Otherwise, filename is usually more specific to the actual link (version, group, etc.)
        return filename

    async def check_links(self, session: AsyncSession, raw_links: List[str], source_url: str, source_name: str, 
                          override_filename: str = None, override_title: str = None, override_year: int = None, 
                          tags: List[str] = None, category: str = None) -> List[DownloadLink]:
        """
        Manages link verification and database insertion with duplicate prevention.
        """
        if not raw_links: return []
        
        # 1. Clean and deduplicate incoming list
        cleaned_links = set()
        for l in raw_links:
            if not l: continue
            url = l.strip()
            # Clean 1fichier affiliate links
            if "1fichier.com" in url:
                url = re.sub(r'&af=\d+', '', url)
            cleaned_links.add(url)
            
        raw_links = list(cleaned_links)

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
            
            if status == "error":
                err_msg = info.get("error", "Unknown hoster error").strip() or "Hoster check failed"
                try:
                    from app.db.models import ScrapedURL
                    async with session.begin_nested():
                        # We don't overwrite if it already exists, just insert/update
                        q_scraped = await session.execute(select(ScrapedURL).where(ScrapedURL.url == link))
                        scraped_existing = q_scraped.scalar_one_or_none()
                        if scraped_existing:
                            scraped_existing.status = f"failed: {err_msg[:100]}"
                            scraped_existing.last_scraped = datetime.now(timezone.utc)
                            scraped_existing.source_name = "Hoster-Check"
                        else:
                            session.add(ScrapedURL(url=link, source_name="Hoster-Check", status=f"failed: {err_msg[:100]}"))
                        await session.flush()
                except Exception as e:
                    print(f"[LINK] Failed to record hoster error for {link}: {e}")

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
                        
                        # Determine best raw_title for tooltips
                        existing.raw_title = self._get_best_raw_title(override_title, final_filename, link)
                        
                        if category:
                            existing.category = category
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
                            title=override_title, 
                            raw_title=self._get_best_raw_title(override_title, final_filename, link),
                            year=override_year,
                            category=category,
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
