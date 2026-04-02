import PTN
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import DownloadLink

class Categorizer:
    @staticmethod
    async def enrich_links(session: AsyncSession):
        """
        Extracts metadata (Title, Season, Quality...) for all RAW links
        (those that don't have a 'title' yet).
        """
        # 1. Look for links to process
        stmt = select(DownloadLink).where(DownloadLink.title == None)
        q = await session.execute(stmt)
        links = q.scalars().all()
        
        if not links:
            print("[CATEGORIZER] No raw links to enrich.")
            return

        print(f"[CATEGORIZER] Enriching {len(links)} raw links...")

        for link in links:
            # Parse the filename
            p = PTN.parse(link.filename)
            
            # Enrich the DownloadLink object directly
            link.title = p.get('title', link.filename)
            link.category = "series" if p.get('season') is not None else "movie"
            link.year = p.get('year')
            
            # Handle lists for season/episode (e.g., S01E01-02)
            seasons = p.get('season')
            if isinstance(seasons, list):
                link.season = ", ".join(map(str, seasons))
            else:
                link.season = str(seasons) if seasons is not None else None
            
            episodes = p.get('episode')
            if isinstance(episodes, list):
                link.episode = ", ".join(map(str, episodes))
            else:
                link.episode = str(episodes) if episodes is not None else None
            
            res = p.get('resolution')
            if not res and ("4KLIGHT" in link.filename.upper()):
                res = "4KLIGHT"
            link.resolution = str(res) if res else None
            link.quality = p.get('quality')
            link.codec = p.get('codec')
            
            # Handle languages + MULTI
            langs = p.get('language', [])
            if isinstance(langs, str):
                langs = [langs]
            
            # Manual MULTI detection
            fn_up = link.filename.upper()
            is_multi = p.get('multi') or ".MULTI." in fn_up or "_MULTI_" in fn_up or "-MULTI-" in fn_up
            
            if is_multi and "MULTI" not in [l.upper() for l in langs]:
                langs.append("MULTI")
            
            link.language = ", ".join(langs) if langs else None
            
            p_res = f"({link.resolution})" if link.resolution else f"({link.quality})"
            p_lang = f" [{link.language}]" if link.language else ""
            print(f"[CATEGORIZER] Enriched: {link.title} {p_res}{p_lang}")

        print(f"[CATEGORIZER] Done.")
