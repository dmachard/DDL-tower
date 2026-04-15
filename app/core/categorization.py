from typing import List
from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import DownloadLink, MediaMetadata
from app.services.tmdb import tmdb_service
from app.services.translation import translation_service

import PTN

import re
import os
import html
from pathlib import Path

class Categorizer:
    @staticmethod
    def _clean_network_name(name: str) -> str:
        """Normalizes network names for better UI display."""
        if not name:
            return name
        
        mapping = {
            "Disney Plus": "Disney+",
            "Amazon Studios": "Amazon",
            "Amazon Prime": "Amazon",
            "HBO Max": "HBO",
            "Apple TV Plus": "Apple TV+",
            "Paramount Plus": "Paramount+"
        }
        return mapping.get(name, name)

    @staticmethod
    def _extract_v_quality(filename: str) -> str:
        """Detects HDR, DV, etc. from filename."""
        if not filename:
            return None
        
        fn = filename.upper()
        tags = []
        
        # Check for Dolby Vision
        if any(x in fn for x in ["DV", "DOVI", "DOLBY VISION", "DOLBY-VISION"]):
            tags.append("DV")
            
        # Check for HDR
        if any(x in fn for x in ["HDR", "HDR10", "HDR10PLUS", "HDR10+"]):
            tags.append("HDR")
            
        # Check for HLG
        if "HLG" in fn:
            tags.append("HLG")
            
        if not tags:
            return None
            
        # Remove duplicates and join (case like DV.HDR)
        return " ".join(sorted(list(set(tags)), reverse=True))

    @staticmethod
    def _clean_search_title(title: str) -> str:
        """
        Cleans the title for better TMDb matching.
        Removes Common noise like Vol. X, Volume X, Part X, Integrale, etc.
        """
        if not title:
            return title
            
        # 1. Replace dots and underscores with spaces
        t = title.replace('.', ' ').replace('_', ' ')
        
        # 2. Remove common noise patterns (case insensitive)
        # Vol 1, Vol. 1, Volume 1, Vol4 etc.
        t = re.sub(r'\b(vol|volume|part|partie|pt)\.?\s*\d+\b', '', t, flags=re.I)
        # French ordinals: 1er, 2e, 3e partie / volet
        t = re.sub(r'\b\d+(?:er|e|eme|ème)\s+(?:partie|volet)\b', '', t, flags=re.I)
        # English written numbers: Part One, Part Two...
        t = re.sub(r'\b(?:part|pt)\.?\s+(?:one|two|three|four|five|six|seven|eight|nine|ten)\b', '', t, flags=re.I)
        # Integrale, Intégrale, Pack, Complet
        t = re.sub(r'\b(int[ée]grale|pack|complet)\b', '', t, flags=re.I)
        
        # 3. Remove 4-digit year at the end (e.g. "Movie Name 1986")
        t = re.sub(r'\s+\d{4}$', '', t)
        
        # 3. Clean up extra punctuation left over
        t = t.replace('-', ' ').replace(':', ' ').replace(',', ' ')
        t = re.sub(r'\s+', ' ', t).strip()
        
        return t

    @staticmethod
    async def enrich_links(session: AsyncSession, links: List[DownloadLink] = None, force_year: int = None, force_type: str = None, force_imdb_id: str = None):
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
            raw_title = p.get('title', link.filename)
            link.title = html.unescape(raw_title) if raw_title else raw_title
            
            # Category: Force it if provided, otherwise detect
            if force_type:
                link.category = force_type
            else:
                link.category = "series" if p.get('season') is not None else "movie"
                
            link.year = force_year if force_year is not None else p.get('year')
            
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
            link.network = Categorizer._clean_network_name(p.get('network')) or ""
            link.v_quality = Categorizer._extract_v_quality(link.filename) or ""
            
            # Handle languages + Scraper Tags + MULTI
            langs = p.get('language', [])
            if isinstance(langs, str):
                langs = [langs]
            
            # 1. Add existing tags already in DB (from Scraper)
            if link.language:
                existing_tags = [t.strip() for t in link.language.split(",") if t.strip()]
                for et in existing_tags:
                    if et.upper() not in [l.upper() for l in langs]:
                        langs.append(et)

            # 2. Manual MULTI detection
            fn_up = link.filename.upper()
            is_multi = p.get('multi') or ".MULTI." in fn_up or " MULTI " in fn_up
            if is_multi and "MULTI" not in [l.upper() for l in langs]:
                langs.append("MULTI")
            
            # 3. Manual VOST detection
            is_vostfr = ".VOSTFR." in fn_up or " VOSTFR " in fn_up or " VOSTFR" in fn_up
            if is_vostfr and "VOST" not in [l.upper() for l in langs]:
                langs.append("VOST")
            
            link.language = ", ".join(langs) if langs else None
            
            p_res = f"({link.resolution})" if link.resolution else f"({link.quality})"
            p_lang = f" [{link.language}]" if link.language else ""
            print(f"[CATEGORIZER] Enriched: {link.title} {p_res}{p_lang}")

        # --- TMDb Metadata Enrichment ---
        # 1. Identify unique (title, year, category) triplets that need metadata
        metadata_needed = {}
        for link in processed_links:
            if link.title and (not link.imdb_id or link.imdb_id == "N/A"):
                key = (link.title, link.year, link.category)
                if key not in metadata_needed:
                    metadata_needed[key] = []
                metadata_needed[key].append(link)
        
        if metadata_needed:
            print(f"[CATEGORIZER] Fetching external metadata for {len(metadata_needed)} unique titles...")
            
            for (title, year, cat), links_to_update in metadata_needed.items():
                # Optimization: Find an existing MediaMetadata in the DB by title AND year
                stmt = select(MediaMetadata).where(MediaMetadata.official_title == title)
                if year:
                    stmt = stmt.where(MediaMetadata.year == year)
                
                existing_meta = (await session.execute(stmt.limit(1))).scalar()
                
                # Poster Watchdog: If metadata exists but the poster file is missing from disk, re-fetch
                if existing_meta and existing_meta.poster_path:
                    # poster_path is usually "static/posters/imdb_id.jpg"
                    # We check in "data/posters/imdb_id.jpg"
                    p_filename = os.path.basename(existing_meta.poster_path)
                    p_disk_path = Path("data/posters") / p_filename
                    if not p_disk_path.exists():
                        print(f"[CATEGORIZER] Poster missing on disk for '{title}' ({p_disk_path}), re-fetching...")
                        existing_meta = None

                if not existing_meta:
                    # Clean title for search
                    search_title = Categorizer._clean_search_title(title)
                    if search_title != title:
                        print(f"[CATEGORIZER] Searching with cleaned title: '{search_title}' (original: '{title}')")
                    
                    # 1. Try direct ID lookup if forced
                    res_data = None
                    if force_imdb_id:
                        print(f"[CATEGORIZER] Using forced IMDB ID: {force_imdb_id}")
                        res_data = await tmdb_service.fetch_metadata_by_imdb_id(force_imdb_id, title, year)

                    # 2. TMDB Search (Primary & Only provider)
                    if not res_data:
                        res_data = await tmdb_service.fetch_metadata(search_title, year, cat)
                        if res_data:
                            print(f"[TMDB] Found match: {res_data.get('official_title')} ({res_data.get('year')})")
                    
                    if res_data:
                        i_id = res_data.get("imdb_id")
                        p_url = res_data.get("poster_url")

                        # Generate a safe local ID if TMDb didn't provide an IMDb ID
                        local_id = i_id
                        if not local_id:
                            # Clean title: keep only alphanumeric and replace spaces with underscores, max 40 chars
                            clean_t = re.sub(r'[^a-zA-Z0-9\s]', '', title).lower()
                            local_id = f"local_{clean_t.replace(' ', '_')}"[:40]
                        
                        poster_id = local_id

                        # 1. Search by i_id first (if available)
                        if i_id:
                            stmt = select(MediaMetadata).where(MediaMetadata.imdb_id == i_id).limit(1)
                            existing_meta = (await session.execute(stmt)).scalar()
                        
                        # Plot handling
                        plot_en = res_data.get("plot_en") or res_data.get("plot")
                        plot_fr = res_data.get("plot_fr")
                        if plot_en and not plot_fr:
                            plot_fr = await translation_service.translate(plot_en)
                        elif not plot_en and plot_fr:
                            plot_en = plot_fr 

                        if not existing_meta:
                            # Final safety check for local_id uniqueness
                            stmt_local = select(MediaMetadata).where(MediaMetadata.imdb_id == local_id).limit(1)
                            existing_meta = (await session.execute(stmt_local)).scalar()

                        if not existing_meta:
                            local_path = None
                            if p_url and p_url != "N/A":
                                local_path = await tmdb_service.download_poster(poster_id, p_url)
                            
                            existing_meta = MediaMetadata(
                                imdb_id=local_id,
                                official_title=res_data.get("official_title"),
                                title_fr=res_data.get("title_fr"),
                                year=res_data.get("year"),
                                poster_path=local_path,
                                plot_en=plot_en,
                                plot_fr=plot_fr,
                                rating=res_data.get("rating")
                            )
                            session.add(existing_meta)
                            await session.flush() 
                        else:
                            # Update existing record
                            if p_url and p_url != "N/A" and (not existing_meta.poster_path or existing_meta.poster_path == ""):
                                existing_meta.poster_path = await tmdb_service.download_poster(existing_meta.imdb_id, p_url)
                            
                            # Sync titles (especially for French priority)
                            if res_data.get("official_title") and existing_meta.official_title != res_data.get("official_title"):
                                existing_meta.official_title = html.unescape(res_data.get("official_title"))
                            
                            if res_data.get("title_fr") and existing_meta.title_fr != res_data.get("title_fr"):
                                existing_meta.title_fr = html.unescape(res_data.get("title_fr"))

                            # Fill other gaps
                            if not existing_meta.plot_fr and plot_fr:
                                existing_meta.plot_fr = plot_fr
                            if not existing_meta.plot_en and plot_en:
                                existing_meta.plot_en = plot_en
                            if not existing_meta.year and res_data.get("year"):
                                existing_meta.year = res_data.get("year")
                            if not existing_meta.rating and res_data.get("rating"):
                                existing_meta.rating = res_data.get("rating")
                
                if existing_meta:
                    for l in links_to_update:
                        l.imdb_id = existing_meta.imdb_id
                        # Use the official title to keep thing standardized
                        if existing_meta.official_title:
                            l.title = existing_meta.official_title
                        if existing_meta.year:
                            l.year = existing_meta.year
                else:
                    # Mark as N/A to avoid retrying every time during repair
                    for l in links_to_update:
                        if not l.imdb_id:
                            l.imdb_id = "N/A"

        print(f"[CATEGORIZER] Done.")
        
    @staticmethod
    async def repair_metadata(session: AsyncSession):
        """
        Scans MediaMetadata for missing fields (poster, plot_fr) and tries to re-fetch them.
        """
        stmt = select(MediaMetadata).where(
            or_(
                MediaMetadata.poster_path == None,
                MediaMetadata.poster_path == "",
                MediaMetadata.title_fr == None,
                MediaMetadata.title_fr == "",
                MediaMetadata.plot_fr == None,
                MediaMetadata.plot_fr == "",
                MediaMetadata.rating == None,
                MediaMetadata.rating == "",
                MediaMetadata.imdb_id == "N/A",
                # Also repair if the official title was incorrectly set to the French title (old bug)
                and_(MediaMetadata.official_title == MediaMetadata.title_fr, MediaMetadata.title_fr != None, MediaMetadata.title_fr != "")
            )
        )
        result = await session.execute(stmt)
        to_repair = result.scalars().all()
        
        if not to_repair:
            print("[CATEGORIZER] No metadata records need repair.")
            return

        print(f"[CATEGORIZER] Scanning {len(to_repair)} identified records for missing info...")
        
        # Poster Watchdog inside Repair: check if files exist on disk for ALL records that have a path
        # to ensure we don't have broken links in the UI.
        stmt_all = select(MediaMetadata).where(MediaMetadata.poster_path != None, MediaMetadata.poster_path != "")
        all_with_posters = (await session.execute(stmt_all)).scalars().all()
        
        watchdog_triggered = 0
        for meta in all_with_posters:
            p_filename = os.path.basename(meta.poster_path)
            # posters are in settings.POSTER_DIR (usually /app/data/posters)
            from app.core.config import settings
            p_disk_path = Path(settings.POSTER_DIR) / p_filename
            
            if not p_disk_path.exists():
                print(f"[CATEGORIZER] Poster missing on disk for '{meta.official_title}' ({p_disk_path}), clearing path to force re-download...")
                meta.poster_path = None
                if meta not in to_repair:
                    to_repair.append(meta)
                watchdog_triggered += 1
            elif "static/posters/" in meta.poster_path:
                # Normalize legacy paths
                meta.poster_path = meta.poster_path.replace("static/posters/", "posters/")
        
        if watchdog_triggered:
            await session.commit()
            print(f"[CATEGORIZER] Watchdog triggered for {watchdog_triggered} missing posters.")

        if not to_repair:
            print("[CATEGORIZER] No metadata records need repair.")
            return

        print(f"[CATEGORIZER] Attempting to repair {len(to_repair)} metadata records...")
        
        for meta in to_repair:
            print(f"[CATEGORIZER] Repairing: {meta.official_title} ({meta.imdb_id})")
            
            # 1. Try TMDb by IMDB ID
            res_data = None
            try:
                # Use cleaned title for more reliable fallback search
                clean_title = Categorizer._clean_search_title(meta.official_title)
                res_data = await tmdb_service.fetch_metadata_by_imdb_id(
                    imdb_id=meta.imdb_id,
                    title=clean_title,
                    year=meta.year
                )
            except Exception as e:
                print(f"[CATEGORIZER] TMDb error for {meta.imdb_id}: {e}")
            
            if not res_data:
                print(f"[CATEGORIZER] All providers failed for {meta.imdb_id}, marking fields as tried.")
                # Mark fields as tried (empty string) to avoid retrying every time
                if meta.poster_path is None: meta.poster_path = ""
                if meta.title_fr is None: meta.title_fr = ""
                if meta.plot_fr is None: meta.plot_fr = ""
                if meta.rating is None: meta.rating = ""
                await session.commit()
                continue
                
            # Update missing fields (Set to "" if still missing to avoid endless retry)
            # We use "" instead of "N/A" to avoid displaying "N/A" in the UI
            updated_fields = []
            if (not meta.poster_path):
                p_url = res_data.get("poster_url")
                if p_url and p_url != "N/A":
                    meta.poster_path = await tmdb_service.download_poster(meta.imdb_id, p_url)
                    updated_fields.append("poster")
                else:
                    meta.poster_path = "" # Explicitly mark as tried
            
            if (not meta.plot_fr):
                plot_en = res_data.get("plot_en") or res_data.get("plot")
                plot_fr = res_data.get("plot_fr")
                if plot_en and not plot_fr:
                    plot_fr = await translation_service.translate(plot_en)
                
                if plot_fr:
                    meta.plot_fr = plot_fr
                    updated_fields.append("plot_fr")
                else:
                    meta.plot_fr = "" # Explicitly mark as tried

            if (not meta.title_fr):
                if res_data.get("title_fr"):
                    meta.title_fr = res_data.get("title_fr")
                    updated_fields.append("title_fr")
                else:
                    meta.title_fr = "" # Explicitly mark as tried
            
            if (not meta.rating):
                if res_data.get("rating"):
                    meta.rating = res_data.get("rating")
                    updated_fields.append("rating")
                else:
                    meta.rating = "" # Explicitly mark as tried

            if updated_fields:
                print(f"[CATEGORIZER] Updated: {', '.join(updated_fields)}")
            else:
                print(f"[CATEGORIZER] No new info found on TMDb, marked missing fields as N/A.")
            
            await session.commit()

    @staticmethod
    async def repair_links_metadata(session: AsyncSession):
        """
        Scans DownloadLinks where metadata fields (like the new 'network' column) 
        are missing and re-parses them from the filename.
        """
        # Target only links missing tech metadata OR with HTML entities in title
        stmt = select(DownloadLink).where(
            (DownloadLink.filename != None),
            or_(
                DownloadLink.imdb_id == None,
                DownloadLink.imdb_id == "N/A",
                DownloadLink.network == None,
                DownloadLink.network == "",
                DownloadLink.v_quality == None,
                DownloadLink.v_quality == "",
                DownloadLink.title.ilike("%&#%")
            )
        )
        result = await session.execute(stmt)
        to_repair = result.scalars().all()

        if not to_repair:
            print("[CATEGORIZER] No link metadata needs repair.")
            return

        print(f"[CATEGORIZER] Attempting to repair tech metadata for {len(to_repair)} links...")
        
        for link in to_repair:
            # 0. Clean HTML Entities in current title (requested by user)
            if link.title:
                link.title = html.unescape(link.title)

            # 1. Technical re-parsing from filename (PTN)
            p = PTN.parse(link.filename)
            
            # Update title from PTN (and unescape it)
            raw_p_title = p.get('title')
            if raw_p_title:
                link.title = html.unescape(raw_p_title)
            
            # Update network (FORCE update to apply normalization)
            net = Categorizer._clean_network_name(p.get('network'))
            if net:
                link.network = net
            else:
                link.network = "" # Mark as tried
            
            # Update visual quality (HDR/DV)
            vq = Categorizer._extract_v_quality(link.filename)
            if vq:
                link.v_quality = vq
            else:
                link.v_quality = "" # Mark as tried
                
            # Update other fields if missing
            if not link.codec and p.get('codec'):
                link.codec = p.get('codec')
            if not link.quality and p.get('quality'):
                link.quality = p.get('quality')
            if not link.resolution and p.get('resolution'):
                link.resolution = str(p.get('resolution'))

            # 2. Alignment with official metadata (IMDb)
            if link.imdb_id:
                stmt_m = select(MediaMetadata).where(MediaMetadata.imdb_id == link.imdb_id)
                meta = (await session.execute(stmt_m)).scalar()
                if meta:
                    # Sync title ONLY if meta has a real title (ignore empty strings)
                    if meta.official_title and meta.official_title != "" and link.title != meta.official_title:
                        link.title = meta.official_title
                    if meta.year and link.year != meta.year:
                        link.year = meta.year

        await session.commit()
        
        # 3. For links still missing IMDb ID, attempt a full enrichment (TMDb search)
        still_missing_imdb = [l for l in to_repair if not l.imdb_id or l.imdb_id == "N/A"]
        if still_missing_imdb:
            print(f"[CATEGORIZER] Retrying TMDb enrichment for {len(still_missing_imdb)} links...")
            await Categorizer.enrich_links(session, still_missing_imdb)
            await session.commit()

        print(f"[CATEGORIZER] Finished link metadata repair.")
