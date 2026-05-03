from datetime import datetime, timezone
from sqlalchemy import select, or_
from app.db.database import AsyncSessionLocal
from app.db.models import DownloadLink, MediaMetadata
from app.core.hoster import Hoster
from app.services.enrichment_service import enrichment_service
from app.core.utils import format_size

class LinkCommands:
    @staticmethod
    async def reverify():
        print("--- [LINKS] Starting re-verification of dead links ---")
        hoster = Hoster()
        
        async with AsyncSessionLocal() as session:
            stmt = select(DownloadLink).where(DownloadLink.status == "dead")
            dead_links = (await session.execute(stmt)).scalars().all()
            
            if not dead_links:
                print("[LINKS] No dead links found.")
                return

            print(f"[LINKS] Found {len(dead_links)} dead links to check.")
            batch_size = 50
            for i in range(0, len(dead_links), batch_size):
                batch = dead_links[i:i + batch_size]
                urls = [link.url for link in batch]
                results = await hoster.check_links(urls)
                recovered_count = 0
                for link_obj in batch:
                    info = results.get(link_obj.url)
                    if info and info.get("status") == "alive":
                        link_obj.status = "alive"
                        link_obj.filename = info.get("filename")
                        link_obj.hoster = info.get("host", "unknown")
                        link_obj.size_bytes = info.get("size", 0)
                        link_obj.size = format_size(link_obj.size_bytes)
                        link_obj.last_checked = datetime.now(timezone.utc)
                        await enrichment_service.enrich_links(session, links=[link_obj])
                        recovered_count += 1
                await session.commit()
                print(f"[LINKS] Batch finished. {recovered_count} links recovered.")

    @staticmethod
    async def view(query: str):
        CLR_T = "\033[96m" # Cyan
        CLR_G = "\033[92m" # Green
        CLR_R = "\033[91m" # Red
        CLR_RESET = "\033[0m"

        print(f"--- [LINKS] Search results for: '{query}' ---")
        async with AsyncSessionLocal() as session:
            stmt = select(DownloadLink).where(or_(
                DownloadLink.title.ilike(f"%{query}%"),
                DownloadLink.filename.ilike(f"%{query}%")
            ))
            m_res = await session.execute(select(MediaMetadata).where(or_(
                MediaMetadata.official_title.ilike(f"%{query}%"),
                MediaMetadata.imdb_id == query
            )).limit(1))
            m_meta = m_res.scalar()
            
            if m_meta:
                stmt = select(DownloadLink).where(or_(
                    DownloadLink.title.ilike(f"%{query}%"),
                    DownloadLink.filename.ilike(f"%{query}%"),
                    DownloadLink.imdb_id == m_meta.imdb_id
                ))
                
            links = (await session.execute(stmt)).scalars().all()
            if not links:
                print(f"No match found for '{query}'.")
                return

            groups = {}
            for link in links:
                key = link.imdb_id if link.imdb_id else f"{link.title}-{link.year}"
                if key not in groups: groups[key] = []
                groups[key].append(link)

            print(f"Found {len(links)} records in {len(groups)} groups.\n")

            for key, group_links in groups.items():
                meta = None
                if group_links[0].imdb_id:
                    meta = (await session.execute(select(MediaMetadata).where(MediaMetadata.imdb_id == group_links[0].imdb_id))).scalar()
                
                title = meta.official_title if meta else group_links[0].title
                year = meta.year if meta else group_links[0].year
                i_id = meta.imdb_id if meta else "No ID"
                
                print(f"{CLR_T}=== {title} ({year}) [{i_id}] ==={CLR_RESET}")
                if meta and meta.plot_fr: print(f"Plot: {meta.plot_fr[:160]}...")
                print(f"{'ID':<6} | {'Qual/Res':<15} | {'Lang':<6} | {'Size':<9} | {'Hoster':<12} | {'Status'}")
                print("-" * 80)
                
                for link in group_links:
                    status_clr = CLR_G if link.status == "alive" else CLR_R
                    q_r = f"{link.quality or '?'}/{link.resolution or '?'}"
                    print(f"{link.id:<6} | {q_r:<15} | {link.language or '?' :<6} | {link.size or '?' :<9} | {link.hoster or '?' :<12} | {status_clr}{link.status.upper()}{CLR_RESET}")
                    print(f"  > {link.filename}")
                    print(f"  > {link.url}")
                print("\n")
