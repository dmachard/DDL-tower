from fastapi import APIRouter, Depends, Response, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import html

from app.db.database import get_db
from app.services.release_service import release_service
from app.core.config import settings

router = APIRouter()

@router.get("/rss")
async def get_rss_feed(
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
        cat = item.get("category", "movie")
        
        # Get available resolutions from the groups
        resolutions = list(item.get("resolutions", {}).keys())
        res_str = f" [{', '.join(resolutions)}]" if resolutions else ""
        
        display_title = f"{title}"
        if year: display_title += f" ({year})"
        display_title += f" [{cat.capitalize()}]{res_str}"
        
        # Build description
        plot = item.get("plot_fr") or item.get("plot_en") or "Pas de description disponible."
        description = f"<p>{plot}</p>"
        if item.get("rating"):
            description += f"<p><strong>Note :</strong> {item['rating']}/10</p>"
        
        # Create a unique link
        # We use the source_url of the first release found as the item link
        # or fallback to a local link
        link = "#"
        if item.get("resolutions"):
            first_res = list(item["resolutions"].values())[0]
            if first_res and len(first_res) > 0:
                link = first_res[0].get("source_url") or "#"

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
        </item>""")

    rss_xml = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
    <title>{html.escape(settings.APP_NAME)} - Latest Releases</title>
    <link>http://localhost:8001</link>
    <description>Dernières releases indexées par DDL Tower</description>
    <language>fr-fr</language>
    <lastBuildDate>{datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")}</lastBuildDate>
    {"".join(rss_items)}
</channel>
</rss>"""

    return Response(content=rss_xml, media_type="application/rss+xml")
