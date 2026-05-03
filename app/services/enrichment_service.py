import re
import os
import html
from typing import List, Optional, Tuple, Dict
from pathlib import Path
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DownloadLink, MediaMetadata
from app.services.tmdb import tmdb_service
from app.services.translation import translation_service
from app.services.parser_service import parser_service
from app.core.config import settings

class EnrichmentService:
    @staticmethod
    async def enrich_links(session: AsyncSession, links: List[DownloadLink] = None, force_year: int = None, force_type: str = None, force_imdb_id: str = None):
        """
        Entry point to orchestrate filename parsing and TMDb enrichment for a list of links.
        If no links are provided, it fetches all links that are missing metadata.
        """
        from sqlalchemy import or_, and_
        if links is None:
            # Fix: Ignore links with empty or null filenames to avoid infinite loops on junk data
            stmt = select(DownloadLink).where(
                and_(
                    DownloadLink.filename != None,
                    DownloadLink.filename != "",
                    or_(
                        DownloadLink.imdb_id == None,
                        DownloadLink.imdb_id == "N/A"
                    ),
                    or_(
                        DownloadLink.title == None,
                        DownloadLink.title == ""
                    )
                )
            )
            q = await session.execute(stmt)
            processed_links = q.scalars().all()
        else:
            processed_links = links
            
        if not processed_links:
            return

        await enrichment_service.process_batch(session, processed_links, force_year, force_type, force_imdb_id)

    @staticmethod
    async def enrich_link_metadata(session: AsyncSession, link: DownloadLink, force_year: int = None, force_type: str = None, force_imdb_id: str = None):
        """
        Enriches a single link by fetching metadata from TMDb.
        """
        if not link.title:
            return
            
        # 1. Check for existing metadata in DB
        stmt = select(MediaMetadata).where(MediaMetadata.official_title == link.title)
        if link.year:
            stmt = stmt.where(MediaMetadata.year == link.year)
        
        existing_meta = (await session.execute(stmt.limit(1))).scalar()
        
        # 2. Re-fetch if poster is missing from disk
        if existing_meta and existing_meta.poster_path:
            p_filename = os.path.basename(existing_meta.poster_path)
            p_disk_path = Path(settings.POSTER_DIR) / p_filename
            if not p_disk_path.exists():
                existing_meta = None

        if not existing_meta:
            search_title = parser_service.clean_search_title(link.title)
            print(f"[ENRICHMENT] 🔍 Searching TMDb for: {search_title} ({link.year or 'any year'})")
            res_data = None
            
            if force_imdb_id:
                res_data = await tmdb_service.fetch_metadata_by_imdb_id(force_imdb_id, link.title, link.year)
            
            if not res_data:
                res_data = await tmdb_service.fetch_metadata(search_title, link.year, link.category)
            
            if res_data:
                official_title = res_data.get("official_title")
                print(f"[ENRICHMENT] ✅ Found match: {official_title} ({res_data.get('year')})")
                imdb_id = res_data.get("imdb_id")
                if not imdb_id:
                    clean_t = re.sub(r'[^a-zA-Z0-9\s]', '', link.title).lower()
                    imdb_id = f"local_{clean_t.replace(' ', '_')}"[:40]
                
                # Check for existing meta with this ID
                stmt_id = select(MediaMetadata).where(MediaMetadata.imdb_id == imdb_id).limit(1)
                existing_meta = (await session.execute(stmt_id)).scalar()

                # Prep plots
                plot_en = res_data.get("plot_en") or res_data.get("plot")
                plot_fr = res_data.get("plot_fr")
                if plot_en and not plot_fr:
                    plot_fr = await translation_service.translate(plot_en)
                elif not plot_en and plot_fr:
                    plot_en = plot_fr
                
                if not existing_meta:
                    p_url = res_data.get("poster_url")
                    local_path = None
                    if p_url and p_url != "N/A":
                        local_path = await tmdb_service.download_poster(imdb_id, p_url)
                    
                    existing_meta = MediaMetadata(
                        imdb_id=imdb_id,
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
                    # Update existing
                    if res_data.get("poster_url") and not existing_meta.poster_path:
                         existing_meta.poster_path = await tmdb_service.download_poster(existing_meta.imdb_id, res_data.get("poster_url"))
                    if res_data.get("official_title"): existing_meta.official_title = html.unescape(res_data.get("official_title"))
                    if res_data.get("title_fr"): existing_meta.title_fr = html.unescape(res_data.get("title_fr"))
                    if not existing_meta.plot_fr and plot_fr: existing_meta.plot_fr = plot_fr
                    if not existing_meta.plot_en and plot_en: existing_meta.plot_en = plot_en
                    if not existing_meta.year: existing_meta.year = res_data.get("year")
                    if not existing_meta.rating: existing_meta.rating = res_data.get("rating")
        
        if existing_meta:
            link.imdb_id = existing_meta.imdb_id
            if existing_meta.official_title: link.title = existing_meta.official_title
            if existing_meta.year: link.year = existing_meta.year
        else:
            # Generate a local ID based on title to avoid grouping everything under "N/A"
            clean_t = re.sub(r'[^a-zA-Z0-9\s]', '', link.title or "unknown").lower().strip()
            link.imdb_id = f"local_{clean_t.replace(' ', '_')}"[:40]

    @staticmethod
    async def process_batch(session: AsyncSession, links: List[DownloadLink], force_year: int = None, force_type: str = None, force_imdb_id: str = None):
        """
        Processes a batch of links for enrichment.
        """
        print(f"[ENRICHMENT] Processing {len(links)} links for enrichment...")
        # First, ensure all links have technical parsing done
        count = 0
        for link in links:
            parse_target = link.title if link.title else link.filename
            if not parse_target or len(parse_target) < 3:
                continue
                
            p = parser_service.parse_filename(parse_target)
            
            # If we have both, compare titles. If they are completely different, 
            # the scraper might have assigned a wrong group title.
            if link.title and link.filename:
                p_file = parser_service.parse_filename(link.filename)
                
                # Check for word overlap between scraper title and filename title
                scraper_title_clean = p.get("title", "").strip()
                file_title_clean = p_file.get("title", "").strip()
                
                t1 = set(re.findall(r'\w+', scraper_title_clean.lower()))
                
                # Check if any word from scraper title is in the filename
                filename_words = set(re.findall(r'\w+', link.filename.lower()))
                has_overlap = bool(t1.intersection(filename_words))
                
                # Rule: The scraper title is the boss (Override).
                if not scraper_title_clean or len(scraper_title_clean) < 3:
                    p["title"] = file_title_clean
                elif not has_overlap:
                    if p_file.get("season") or p_file.get("episode"):
                        has_vowels = any(c in file_title_clean.lower() for c in 'aeiouy')
                        digit_ratio = sum(c.isdigit() for c in file_title_clean) / len(file_title_clean) if file_title_clean else 0
                        is_junk = (not has_vowels and len(file_title_clean) > 4) or (digit_ratio > 0.4 and len(file_title_clean) > 5)
                        if not is_junk:
                            p["title"] = file_title_clean
                
                # Copy technical details from file if missing in scraper title
                for key in ["resolution", "quality", "codec", "v_quality", "season", "episode", "languages", "year"]:
                    if not p.get(key) and p_file.get(key):
                        p[key] = p_file[key]

            if p:
                if p.get("title"):
                    link.title = p["title"]
                
                if p.get("season") or p.get("episode"):
                    link.category = "series"
                elif not link.category:
                    link.category = "movie"
                
                if force_year is not None: link.year = force_year
                elif not link.year: link.year = p["year"]

                link.season = p["season"]
                link.episode = p["episode"]
                link.resolution = p["resolution"]
                link.quality = p["quality"]
                link.codec = p["codec"]
                link.network = p["network"]
                link.v_quality = p["v_quality"]
                
                # Language merge
                langs = p["languages"]
                if link.language:
                    existing = [t.strip() for t in link.language.split(",") if t.strip()]
                    for et in existing:
                        if et.upper() not in [l.upper() for l in langs]: langs.append(et)
                link.language = ", ".join(langs) if langs else None

        # Group by (title, year, category) to optimize TMDb calls
        needed = {}
        for link in links:
            if link.title and (not link.imdb_id or link.imdb_id == "N/A"):
                key = (link.title, link.year, link.category)
                if key not in needed: needed[key] = []
                needed[key].append(link)
        
        titles_count = 0
        for (title, year, cat), group in needed.items():
            # We just need to enrich ONE link and then copy to others
            base_link = group[0]
            await EnrichmentService.enrich_link_metadata(session, base_link, force_year, force_type, force_imdb_id)
            for other in group[1:]:
                other.imdb_id = base_link.imdb_id
                other.title = base_link.title
                other.year = base_link.year
            
            titles_count += 1
            if titles_count % 20 == 0:
                print(f"[ENRICHMENT] Progress: {titles_count}/{len(needed)} unique titles processed...")

enrichment_service = EnrichmentService()
