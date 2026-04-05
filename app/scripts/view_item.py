import asyncio
import sys
from sqlalchemy.future import select
from sqlalchemy.inspection import inspect
from app.db.database import AsyncSessionLocal
from app.db.models import DownloadLink, MediaMetadata

async def view_item(title: str):
    """
    Search for a title and display ALL its database columns and values.
    """
    async with AsyncSessionLocal() as session:
        # Search by filename or title
        stmt = select(DownloadLink).where(
            (DownloadLink.title == title) | 
            (DownloadLink.filename.like(f"%{title}%"))
        )
        # Also check MediaMetadata for official_title matches
        stmt_m = select(MediaMetadata).where(MediaMetadata.official_title == title).limit(1)
        m_res = await session.execute(stmt_m)
        m_meta = m_res.scalar()
        
        if m_meta:
            # If we found metadata, add its links too
            stmt = select(DownloadLink).where(
                (DownloadLink.title == title) | 
                (DownloadLink.filename.like(f"%{title}%")) |
                (DownloadLink.imdb_id == m_meta.imdb_id)
            )
            
        result = await session.execute(stmt)
        links = result.scalars().all()
        
        if not links:
            print(f"No match found for '{title}'.")
            return

        # Use SQLAlchemy inspection to get column names
        inst = inspect(DownloadLink)
        columns = [c_attr.key for c_attr in inst.mapper.column_attrs]

        print(f"--- Found {len(links)} records ---\n")
        
        for i, link in enumerate(links):
            print(f"RECORD #{i+1}")
            for col in columns:
                if col == 'metadata_rel': continue
                val = getattr(link, col)
                print(f"{col}: {val}")
            
            # Fetch and display metadata details if linked
            if link.imdb_id:
                # We need to ensure metadata is loaded. Since we are in async, 
                # we do a separate query or use selectinload (but separate is simpler here for a script)
                m_stmt = select(MediaMetadata).where(MediaMetadata.imdb_id == link.imdb_id)
                m_res = await session.execute(m_stmt)
                meta = m_res.scalar()
                if meta:
                    print(f"\n--- CENTRALIZED METADATA ({meta.imdb_id}) ---")
                    print(f"official_title: {meta.official_title}")
                    print(f"poster_path: {meta.poster_path}")
                    print(f"plot: {meta.plot}")
            
            print("-" * 20)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 -m app.scripts.view_item \"TITLE\"")
        sys.exit(1)
        
    search_query = sys.argv[1]
    asyncio.run(view_item(search_query))
