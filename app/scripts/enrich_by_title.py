import asyncio
import sys
from sqlalchemy.future import select
from sqlalchemy import or_

from app.db.database import AsyncSessionLocal
from app.db.models import DownloadLink
from app.core.categorization import Categorizer

async def enrich_by_title(title: str):
    """
    Search for links matching a title and trigger their categorization/OMDb enrichment.
    """
    print(f"[MANUAL ENRICHER] Searching for links related to: '{title}'...")
    
    async with AsyncSessionLocal() as session:
        # Search by exact title match (best for precision)
        stmt = select(DownloadLink).where(DownloadLink.title == title)
        result = await session.execute(stmt)
        links = result.scalars().all()
        
        # Fallback: if no titles match exactly, try a more restrictive filename match
        # (Looking for the title followed by a dot or space, or starting with it)
        if not links:
            print(f"[MANUAL ENRICHER] No exact title match for '{title}'. Trying restricted filename search...")
            stmt = select(DownloadLink).where(
                or_(
                    DownloadLink.filename.like(f"{title}.%"),
                    DownloadLink.filename.like(f"{title} %"),
                    DownloadLink.filename.like(f"{title}-%"),
                    DownloadLink.filename == title
                )
            )
            result = await session.execute(stmt)
            links = result.scalars().all()
        
        if not links:
            print(f"[MANUAL ENRICHER] No links found for '{title}'.")
            return
            
        print(f"[MANUAL ENRICHER] Found {len(links)} links. Starting enrichment...")
        
        # Trigger Categorizer (this will handle PTN parsing and OMDb fetch)
        await Categorizer.enrich_links(session, links)
        
        await session.commit()
        print(f"[MANUAL ENRICHER] Successfully enriched and committed {len(links)} links.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 -m app.scripts.enrich_by_title \"TITRE_DU_FILM\"")
        sys.exit(1)
        
    search_title = sys.argv[1]
    asyncio.run(enrich_by_title(search_title))
