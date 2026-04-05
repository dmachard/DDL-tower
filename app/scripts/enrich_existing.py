import asyncio
import argparse
from sqlalchemy import select
from app.db.database import AsyncSessionLocal
from app.db.models import DownloadLink
from app.core.categorization import Categorizer

async def enrich_existing(limit: int):
    """
    Find unique titles in the database that don't have an imdb_id and enrich them.
    """
    async with AsyncSessionLocal() as session:
        print(f"[ENRICHER] Looking for titles needing enrichment (Max: {limit})...")
        
        # 1. Identify unique (title, year, category) triplets without imdb_id
        stmt = select(
            DownloadLink.title, 
            DownloadLink.year, 
            DownloadLink.category
        ).where(
            DownloadLink.imdb_id == None
        ).group_by(
            DownloadLink.title, 
            DownloadLink.year, 
            DownloadLink.category
        ).limit(limit)
        
        result = await session.execute(stmt)
        triplets = result.all()
        
        if not triplets:
            print("[ENRICHER] Everything is already enriched! Good job.")
            return

        print(f"[ENRICHER] Found {len(triplets)} unique titles to enrich in this batch.")
        
        # 2. Process each triplet
        # We can actually use the categorizer's logic directly.
        # It takes a list of DownloadLink objects.
        
        for title, year, category in triplets:
            if not title: continue
            
            print(f"[ENRICHER] Processing: '{title}' ({year} - {category})")
            
            # Fetch ALL links matching this triplet to update them all at once
            link_stmt = select(DownloadLink).where(
                DownloadLink.title == title,
                DownloadLink.year == year,
                DownloadLink.category == category,
                DownloadLink.imdb_id == None
            )
            links_result = await session.execute(link_stmt)
            links = links_result.scalars().all()
            
            if links:
                # Use the real-time enrichment flow of the categorizer
                # It handles OMDb fetching, translation, and DB updates.
                await Categorizer.enrich_links(session, links)
                await session.commit()
                print(f"[ENRICHER] Updated {len(links)} links for '{title}'.")
            
            # Optional: Add a small delay if you want to be extra careful (OMDb is generally fine with 1-2 req/sec)
            # await asyncio.sleep(0.5)

        print(f"[ENRICHER] Batch of {len(triplets)} titles completed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrich existing links with metadata in batches.")
    parser.add_argument("--limit", type=int, default=500, help="Max unique titles to process in this run.")
    args = parser.parse_args()

    asyncio.run(enrich_existing(args.limit))
