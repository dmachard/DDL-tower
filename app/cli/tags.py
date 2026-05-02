from sqlalchemy import select, or_
from app.db.database import AsyncSessionLocal
from app.db.models import DownloadLink, MediaMetadata
from app.core.categorization import Categorizer

class TagCommands:
    @staticmethod
    async def process(title: str = None, rename_to: str = None, year: int = None, media_type: str = None, limit: int = 500, repair: bool = False, imdb_id: str = None):
        async with AsyncSessionLocal() as session:
            if repair:
                await Categorizer.repair_metadata(session)
                await Categorizer.repair_links_metadata(session)
                return

            if title:
                print(f"--- [TAG] Manual tagging for: '{title}' (Year: {year or 'Auto'}, Type: {media_type or 'Auto'}) ---")
                if "%" in title:
                    stmt = select(DownloadLink).where(DownloadLink.title.like(title))
                else:
                    stmt = select(DownloadLink).where(DownloadLink.title == title)
                result = await session.execute(stmt)
                links = result.scalars().all()
                
                if not links:
                    print(f"[TAG] No exact title match for '{title}'. Trying filename search...")
                    stmt = select(DownloadLink).where(or_(
                        DownloadLink.filename.like(f"{title}.%"),
                        DownloadLink.filename.like(f"{title} %"),
                        DownloadLink.filename.like(f"{title}-%"),
                        DownloadLink.filename == title
                    ))
                    links = (await session.execute(stmt)).scalars().all()
                
                if not links:
                    print(f"[TAG] No links found for '{title}'.")
                    return
                
                if rename_to:
                    print(f"[TAG] Renaming {len(links)} links to '{rename_to}'...")
                    for link in links: link.title = rename_to

                for link in links:
                    link.imdb_id = None
                    if year is not None: link.year = year
                    if media_type is not None: link.category = media_type
                        
                await Categorizer.enrich_links(session, links, force_year=year, force_type=media_type, force_imdb_id=imdb_id)
                await session.commit()
                
                display_meta = None
                if links[0].imdb_id:
                    display_meta = (await session.execute(select(MediaMetadata).where(MediaMetadata.imdb_id == links[0].imdb_id))).scalar()

                print(f"[TAG] Successfully tagged {len(links)} links.")
                if display_meta:
                    print(f"\n--- METADATA FOUND ({display_meta.imdb_id}) ---")
                    print(f"Official Title: {display_meta.official_title}")
                    if display_meta.title_fr: print(f"French Title: {display_meta.title_fr}")
                    print(f"Year: {display_meta.year}")
                    print(f"Poster: {display_meta.poster_path or 'None'}")
                    print(f"Plot (FR): {display_meta.plot_fr[:150] if display_meta.plot_fr else 'None'}...")
                else:
                    print("\n[WARNING] No external metadata found.")
            else:
                print(f"--- [TAG] Batch tagging (Limit: {limit}) ---")
                stmt = select(DownloadLink.title, DownloadLink.year, DownloadLink.category).where(DownloadLink.imdb_id == None).group_by(DownloadLink.title, DownloadLink.year, DownloadLink.category).limit(limit)
                triplets = (await session.execute(stmt)).all()
                
                if not triplets:
                    print("[TAG] Everything is already tagged!")
                    return

                for t_title, t_year, t_category in triplets:
                    if not t_title: continue
                    print(f"[TAG] Batch Processing: '{t_title}'")
                    link_stmt = select(DownloadLink).where(DownloadLink.title == t_title, DownloadLink.year == t_year, DownloadLink.category == t_category, DownloadLink.imdb_id == None)
                    links = (await session.execute(link_stmt)).scalars().all()
                    if links:
                        await Categorizer.enrich_links(session, links)
                        await session.commit()
