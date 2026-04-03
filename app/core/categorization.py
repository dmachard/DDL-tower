from typing import List
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import DownloadLink

import PTN

class Categorizer:
    @staticmethod
    async def enrich_links(session: AsyncSession, links: List[DownloadLink] = None):
        """
        Extracts metadata (Title, Season, Quality...) for links.
        If 'links' is provided, it processes only those.
        Otherwise, it scans the database for links without a title (batch fallback).
        """
        if links is None:
            # Batch mode: Look for links without a title in the DB BUT with a filename!
            stmt = select(DownloadLink).where(DownloadLink.title == None, DownloadLink.filename != None)
            q = await session.execute(stmt)
            processed_links = q.scalars().all()
        else:
            processed_links = links
            
        if not processed_links:
            if links is None: # Only log if it was a batch scan
                print("[CATEGORIZER] No raw links for batch enrichment.")
            return

        print(f"[CATEGORIZER] Enriching {len(processed_links)} links (Real-time Flow)...")

        for link in processed_links:
            if not link.filename:
                continue
                
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
