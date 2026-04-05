from typing import List
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import DownloadLink, MediaMetadata
from app.services.omdb import omdb_service
from app.services.tmdb import tmdb_service
from app.services.translation import translation_service

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

        print(f"[CATEGORIZER] Enriching {len(processed_links)} links...")

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
            is_multi = p.get('multi') or ".MULTI." in fn_up or " MULTI " in fn_up
            
            if is_multi and "MULTI" not in [l.upper() for l in langs]:
                langs.append("MULTI")
            
            link.language = ", ".join(langs) if langs else None
            
            p_res = f"({link.resolution})" if link.resolution else f"({link.quality})"
            p_lang = f" [{link.language}]" if link.language else ""
            print(f"[CATEGORIZER] Enriched: {link.title} {p_res}{p_lang}")

        # --- OMDb/TMDb Metadata Enrichment ---
        # 1. Identify unique (title, year, category) triplets that need metadata
        metadata_needed = {}
        for link in processed_links:
            if link.title and not link.imdb_id:
                key = (link.title, link.year, link.category)
                if key not in metadata_needed:
                    metadata_needed[key] = []
                metadata_needed[key].append(link)
        
        if metadata_needed:
            print(f"[CATEGORIZER] Fetching external metadata for {len(metadata_needed)}...")
            
            for (title, year, cat), links_to_update in metadata_needed.items():
                # Optimization: Find an existing MediaMetadata in the DB by title
                stmt = select(MediaMetadata).where(MediaMetadata.official_title == title).limit(1)
                existing_meta = (await session.execute(stmt)).scalar()
                
                if not existing_meta:
                    # 1. Try OMDb API
                    omdb_type = "movie" if cat == "movie" else "series"
                    res_data = await omdb_service.fetch_metadata(title, year, omdb_type)
                    
                    # 2. Fallback to TMDb API if OMDb fails
                    if not res_data:
                        print(f"[CATEGORIZER] OMDb fallback to TMDb for '{title}'...")
                        res_data = await tmdb_service.fetch_metadata(title, year, omdb_type)
                    
                    if res_data:
                        i_id = res_data.get("imdb_id")
                        
                        # Double check if this IMDB ID already exists in MediaMetadata
                        if i_id:
                            stmt = select(MediaMetadata).where(MediaMetadata.imdb_id == i_id).limit(1)
                            existing_meta = (await session.execute(stmt)).scalar()
                        
                        if not existing_meta:
                            # Download poster locally
                            p_url = res_data.get("poster_url")
                            local_path = None
                            if i_id and p_url:
                                local_path = await omdb_service.download_poster(i_id, p_url)
                            
                            # Handle Plots (supporting both OMDb format and TMDb dual-language format)
                            plot_en = res_data.get("plot_en") or res_data.get("plot")
                            plot_fr = res_data.get("plot_fr")
                            
                            # Translate if only English is available
                            if plot_en and not plot_fr:
                                plot_fr = await translation_service.translate(plot_en)
                            elif not plot_en and plot_fr:
                                plot_en = plot_fr # Fallback if only French found

                            existing_meta = MediaMetadata(
                                imdb_id=i_id or f"local_{title.replace(' ', '_').lower()}",
                                official_title=res_data.get("official_title"),
                                year=res_data.get("year"),
                                poster_path=local_path,
                                plot_en=plot_en,
                                plot_fr=plot_fr
                            )
                            session.add(existing_meta)
                            await session.flush() # Ensure ID/Object is ready
                
                if existing_meta:
                    for l in links_to_update:
                        l.imdb_id = existing_meta.imdb_id

        print(f"[CATEGORIZER] Done.")
