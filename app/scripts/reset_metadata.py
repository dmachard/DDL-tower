import asyncio
import argparse
from sqlalchemy import select, update, delete
from app.db.database import AsyncSessionLocal
from app.db.models import DownloadLink, MediaMetadata

async def reset_metadata(title_query: str = None, imdb_id: str = None):
    """
    Reset metadata for links matching a title or IMDb ID.
    This clears the imdb_id in download_links, allowing them to be re-enriched.
    """
    async with AsyncSessionLocal() as session:
        if not title_query and not imdb_id:
            print("[RESET] Error: You must provide --title or --imdb_id.")
            return

        # 1. Clear imdb_id in download_links
        stmt = update(DownloadLink).values(imdb_id=None).where(DownloadLink.imdb_id != None)
        
        if title_query:
            print(f"[RESET] Searching for links with title matching: '{title_query}'...")
            # We match on 'title' (extracted from filename)
            stmt = stmt.where(DownloadLink.title.ilike(f"%{title_query}%"))
        
        if imdb_id:
            print(f"[RESET] Searching for links with IMDb ID: '{imdb_id}'...")
            stmt = stmt.where(DownloadLink.imdb_id == imdb_id)
            
        result = await session.execute(stmt)
        # In a real app we'd get the actual links to find their IDs,
        # but for simplicity let's just commit the update.
        await session.commit()
        affected = result.rowcount
        
        # 2. Cleanup MediaMetadata (using Title matching too if we don't have ID)
        if title_query:
            print(f"[RESET] Cleaning MediaMetadata for title: '{title_query}'...")
            del_stmt = delete(MediaMetadata).where(MediaMetadata.official_title.ilike(f"%{title_query}%"))
            await session.execute(del_stmt)
        
        if imdb_id:
            print(f"[RESET] Deleting metadata entry for '{imdb_id}'...")
            del_stmt = delete(MediaMetadata).where(MediaMetadata.imdb_id == imdb_id)
            await session.execute(del_stmt)

        await session.commit()
        print(f"[RESET] Successfully reset {affected} links. Database entry for metadata cleaned.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reset metadata for one or more links.")
    parser.add_argument("--title", help="Title (or part of title) to reset.")
    parser.add_argument("--imdb_id", help="Exact IMDb ID to reset.")
    args = parser.parse_args()

    asyncio.run(reset_metadata(args.title, args.imdb_id))
