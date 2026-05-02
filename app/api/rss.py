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
        db, page=1, limit=limit, q=q, category=category, recent=True
    )
    items = data.get("items", [])

    rss_items = []
    for item in items:
        # Construct a descriptive title
        # e.g., "Deadpool (2016) [Movie] [1080p, 2160p]"
        title = item.get("official_title") or item.get("title")
        year = item.get("year")
        # Collect all unique tags across all resolutions/cards
        all_tags = set()
        resolutions_dict = item.get("resolutions", {})
        for res, cards in resolutions_dict.items():
            if res and res.lower() not in ["none", "unknown", ""]:
                all_tags.add(res)
            for card in cards:
                for field in ["language", "quality", "codec", "network", "v_quality", "source"]:
                    val = card.get(field)
                    if val and str(val).lower() not in ["none", "unknown", "", "null"]:
                        all_tags.add(str(val))
        
        # Sort tags for a cleaner display
        sorted_tags = sorted(list(all_tags))
        tags_str = f" [{', '.join(sorted_tags)}]" if sorted_tags else ""
        
        cat = item.get("category", "movie") or "movie"
        display_title = f"[{cat.capitalize()}] {title}"
        if year: display_title += f" ({year})"
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

        if item.get("rating"):
            description += f"<p><strong>Note :</strong> {item['rating']}/10</p>"
        
        # Link to the DDL Tower dashboard
        # We use a query parameter 'q' to pre-filter the results
        base_url = str(request.base_url).rstrip("/")
        link = f"{base_url}/?q={urllib.parse.quote(title)}"

        guid = item.get("imdb_id") or f"local_{title}_{year}"
        
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
