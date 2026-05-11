from fastapi import APIRouter, Depends, Response, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import html
import urllib.parse

from app.db.database import get_db
from app.services.release_service import release_service
from app.core.config import settings

router = APIRouter()

@router.get("/rss")
async def get_rss_feed(
    request: Request,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
    category: str = Query(None),
    q: str = Query(None)
):
    """
    Generates an RSS 2.0 feed of the latest releases.
    """
    # Get grouped releases (similar to the dashboard)
    data = await release_service.get_grouped_releases(
        db, page=1, limit=limit, q=q, category=category, recent=False
    )
    items = data.get("items", [])

    rss_items = []
    for item in items:
        # Construct a descriptive title
        # e.g., "Deadpool (2016) [Movie] [1080p, 2160p]"
        title = item.get("title_fr") or item.get("official_title") or item.get("title")
        year = item.get("year")
        # Collect only the tags from the LATEST added versions (to avoid noise from old versions)
        raw_tags = []
        resolutions_dict = item.get("resolutions", {})
        latest_ts = item.get("last_updated")
        
        for res, cards in resolutions_dict.items():
            for card in cards:
                # Compare card's last_checked with group's last_updated
                card_ts = card.get("last_checked")
                card_ts_str = card_ts.isoformat() if hasattr(card_ts, "isoformat") else str(card_ts)
                
                if card_ts_str == latest_ts:
                    if res: raw_tags.extend(str(res).split(','))
                    for field in ["language", "quality", "codec", "network", "v_quality"]:
                        val = card.get(field)
                        if val: raw_tags.extend(str(val).split(','))
        
        # Clean, unique, and case-insensitive deduplication
        unique_tags_map = {}
        for t in raw_tags:
            clean_t = t.strip()
            if clean_t and clean_t.lower() not in ["none", "unknown", "null"]:
                t_lower = clean_t.lower()
                if t_lower not in unique_tags_map:
                    unique_tags_map[t_lower] = clean_t
        
        # Sort tags for a cleaner display
        sorted_tags = sorted(unique_tags_map.values())
        tags_str = f" [{', '.join(sorted_tags)}]" if sorted_tags else ""
        
        # Category label mapping (User requested: Movies -> Film, Series -> TV)
        cat = item.get("category", "movie") or "movie"
        cat_labels = {
            "movie": "Film",
            "series": "TV"
        }
        display_cat = cat_labels.get(cat.lower(), "Film" if "movie" in cat.lower() else "TV")
        
        display_title = f"[{display_cat}]"
        if year: display_title += f" ({year})"
        display_title += f" {title}"
        display_title += tags_str
        
        # Build description
        plot = item.get("plot_fr") or item.get("plot_en") or "Pas de description disponible."
        
        # Poster URL handling
        poster_path = item.get("poster_path")
        poster_url = None
        if poster_path:
            filename = poster_path.split("/")[-1]
            base_url = str(request.base_url).rstrip("/")
            poster_url = f"{base_url}/posters/{filename}"

        description = ""
        if poster_url:
            description += f'<p><img src="{html.escape(poster_url)}" alt="Poster" style="max-width: 300px; display: block; margin-bottom: 10px;" /></p>'
        description += f"<p>{plot}</p>"
        
        # Add original title if different from display title
        orig_title = item.get("official_title")
        if orig_title and orig_title != title:
            description += f"<p><em>Titre original : {html.escape(orig_title)}</em></p>"

        if item.get("rating"):
            description += f"<p><strong>Note :</strong> {item['rating']}/10</p>"
        
        # Add list of files (raw_title)
        files_sections = []
        base_api_url = str(request.base_url).rstrip("/") + "/api"
        
        for res, cards in resolutions_dict.items():
            res_files = []
            for card in cards:
                for sub in card.get("sub_releases", []):
                    rt = sub.get("raw_title")
                    if rt:
                        size_info = f" ({sub.get('total_size')})" if sub.get('total_size') else ""
                        
                        # Links for individual hosters (triggers all parts for that hoster)
                        hoster_to_urls = {}
                        for part in sub.get("parts", []):
                            u = part.get("url")
                            h = part.get("hoster", "Lien")
                            if u:
                                if h not in hoster_to_urls: hoster_to_urls[h] = []
                                hoster_to_urls[h].append(u)
                        
                        hoster_links = []
                        for h, urls in hoster_to_urls.items():
                            trigger_url = f"{base_api_url}/download-link?url={urllib.parse.quote(','.join(urls))}"
                            hoster_links.append(f'<a href="{html.escape(trigger_url)}" style="color: #3498db; font-weight: bold;">[{html.escape(h)}]</a>')
                        
                        res_files.append(f"{rt}{size_info} {' '.join(hoster_links)}")
            
            if res_files:
                unique_res_files = list(dict.fromkeys(res_files))
                files_sections.append(f"<strong>{res} :</strong><ul>" + "".join([f"<li>{f}</li>" for f in unique_res_files]) + "</ul>")
        
        if files_sections:
            description += "<h4>Fichiers disponibles :</h4>" + "".join(files_sections)
        
        # Link to the DDL Tower dashboard
        # We use a query parameter 'q' to pre-filter the results
        base_url = str(request.base_url).rstrip("/")
        link = f"{base_url}/?q={urllib.parse.quote(title)}"

        # Format pubDate (RSS 2.0 requires RFC 822)
        # Using last_updated if available
        last_updated_str = item.get("last_updated")
        if last_updated_str:
            try:
                dt = datetime.fromisoformat(last_updated_str)
                pub_date = dt.strftime("%a, %d %b %Y %H:%M:%S GMT")
            except:
                pub_date = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
        else:
            pub_date = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

        guid_base = item.get("imdb_id") or f"local_{title}_{year}"
        # Include timestamp in GUID so updates (new resolutions/parts) are detected as new by FreshRSS
        guid = f"{guid_base}_{last_updated_str}"

        rss_items.append(f"""
        <item>
            <title>{html.escape(display_title)}</title>
            <link>{html.escape(link)}</link>
            <description>{html.escape(description)}</description>
            <pubDate>{pub_date}</pubDate>
            <guid isPermaLink="false">{html.escape(guid)}</guid>
            {f'<enclosure url="{html.escape(poster_url)}" length="0" type="image/jpeg" />' if poster_url else ''}
            {f'<media:content url="{html.escape(poster_url)}" medium="image" />' if poster_url else ''}
        </item>""")

    rss_xml = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
<channel>
    <title>{html.escape(settings.APP_NAME)} - Latest Releases</title>
    <link>{html.escape(str(request.base_url))}</link>
    <description>Dernières releases indexées par DDL Tower</description>
    <language>fr-fr</language>
    <lastBuildDate>{datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")}</lastBuildDate>
    {"".join(rss_items)}
</channel>
</rss>"""

    return Response(content=rss_xml, media_type="application/rss+xml")

@router.get("/rss/downloads")
async def get_downloads_rss_feed(
    request: Request,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=100)
):
    """
    Generates an RSS 2.0 feed of the download history.
    """
    from app.db.models import DownloadHistory, MediaMetadata
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    
    stmt = select(DownloadHistory).options(
        selectinload(DownloadHistory.metadata_rel)
    ).order_by(DownloadHistory.download_date.desc()).limit(limit)
    
    result = await db.execute(stmt)
    items = result.scalars().all()

    rss_items = []
    for item in items:
        # Title construction
        meta = item.metadata_rel
        title = meta.title_fr if meta and meta.title_fr else (meta.official_title if meta else item.title)
        year = meta.year if meta and meta.year else item.year
        
        display_cat = "Film" if item.category == "movie" else "TV"

        display_title = f"[{display_cat}]"
        if year: display_title += f" ({year})"
        display_title += f" {title}"
        
        # Build description
        plot = meta.plot_fr if meta and meta.plot_fr else (meta.plot_en if meta else "Téléchargement terminé.")
        
        # Poster URL
        poster_url = None
        if meta and meta.poster_path:
            filename = meta.poster_path.split("/")[-1]
            base_url = str(request.base_url).rstrip("/")
            poster_url = f"{base_url}/posters/{filename}"

        description = f"<p>Le fichier <strong>{html.escape(item.filename)}</strong> a été téléchargé avec succès.</p>"
        if poster_url:
            description += f'<p><img src="{html.escape(poster_url)}" alt="Poster" style="max-width: 200px; display: block; margin-bottom: 10px;" /></p>'
        description += f"<p>{plot}</p>"
        
        # Link to the file (if reachable or just to dashboard)
        base_url = str(request.base_url).rstrip("/")
        link = f"{base_url}/?q={urllib.parse.quote(title)}"

        pub_date = item.download_date.strftime("%a, %d %b %Y %H:%M:%S GMT")
        guid = f"history_{item.id}"

        rss_items.append(f"""
        <item>
            <title>{html.escape(display_title)}</title>
            <link>{html.escape(link)}</link>
            <description>{html.escape(description)}</description>
            <pubDate>{pub_date}</pubDate>
            <guid isPermaLink="false">{html.escape(guid)}</guid>
            {f'<enclosure url="{html.escape(poster_url)}" length="0" type="image/jpeg" />' if poster_url else ''}
        </item>""")

    rss_xml = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
<channel>
    <title>{html.escape(settings.APP_NAME)} - Historique des Téléchargements</title>
    <link>{html.escape(str(request.base_url))}</link>
    <description>Liste des derniers films et séries téléchargés</description>
    <language>fr-fr</language>
    <lastBuildDate>{datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")}</lastBuildDate>
    {"".join(rss_items)}
</channel>
</rss>"""

    return Response(content=rss_xml, media_type="application/rss+xml")
