import asyncio
import os
import sys
from datetime import datetime, timezone
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

# Add the project root to sys.path if needed
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.db.database import AsyncSessionLocal
from app.db.models import DownloadLink
from app.core.hoster import Hoster
from app.core.categorization import Categorizer
from app.core.utils import format_size

async def reverify_dead_links():
    """
    Finds all links marked as 'dead', re-checks them,
    and enriches metadata if they are back online.
    """
    print("--- [RE-VERIFIER] Starting re-verification of dead links ---")
    hoster = Hoster()
    categorizer = Categorizer()
    
    async with AsyncSessionLocal() as session:
        # 1. Fetch all dead links
        stmt = select(DownloadLink).where(DownloadLink.status == "dead")
        result = await session.execute(stmt)
        dead_links = result.scalars().all()
        
        if not dead_links:
            print("[RE-VERIFIER] No dead links found in database.")
            return

        print(f"[RE-VERIFIER] Found {len(dead_links)} dead links to check.")
        
        # 2. Process in batches to avoid overwhelming APIs
        batch_size = 50
        for i in range(0, len(dead_links), batch_size):
            batch = dead_links[i:i + batch_size]
            urls = [link.url for link in batch]
            
            print(f"[RE-VERIFIER] Checking batch {i//batch_size + 1}/{(len(dead_links)-1)//batch_size + 1}...")
            
            # Check availability
            results = await hoster.check_links(urls)
            
            recovered_count = 0
            for link_obj in batch:
                info = results.get(link_obj.url)
                if not info:
                    continue
                
                new_status = info.get("status", "dead").lower()
                
                if new_status == "alive":
                    # Link is back! Update its technical info
                    link_obj.status = "alive"
                    link_obj.filename = info.get("filename")
                    link_obj.hoster = info.get("host", "unknown")
                    link_obj.size_bytes = info.get("size", 0)
                    link_obj.size = format_size(link_obj.size_bytes)
                    link_obj.last_checked = datetime.now(timezone.utc)
                    
                    # 3. Categorize it immediately (as it was probably never or badly categorized)
                    # We pass [link_obj] as a list to the categorizer
                    await categorizer.enrich_links(session, links=[link_obj])
                    recovered_count += 1
                    print(f"[RE-VERIFIER] RECOVERED: {link_obj.filename}")
            
            # Commit this batch
            await session.commit()
            if recovered_count > 0:
                print(f"[RE-VERIFIER] Batch finished. {recovered_count} links recovered and categorized.")
            else:
                print(f"[RE-VERIFIER] Batch finished. No links recovered.")

    print("--- [RE-VERIFIER] Finished ---")

if __name__ == "__main__":
    asyncio.run(reverify_dead_links())
