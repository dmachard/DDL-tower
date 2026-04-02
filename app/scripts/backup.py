import asyncio
import json
import os
import sys
from datetime import datetime

# Add the project root to sys.path to allow imports from "app"
sys.path.append(os.getcwd())

from sqlalchemy import select
from app.db.database import AsyncSessionLocal
from app.db.models import DownloadLink, ScrapedURL

def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

async def backup():
    print("--- DDLtower Backup Utility ---")
    async with AsyncSessionLocal() as session:
        # 1. Fetch Links
        stmt_links = select(DownloadLink)
        result_links = await session.execute(stmt_links)
        links = result_links.scalars().all()
        
        # 2. Fetch Scraped URLs
        stmt_scraped = select(ScrapedURL)
        result_scraped = await session.execute(stmt_scraped)
        scraped = result_scraped.scalars().all()
        
        # Structure the data
        data = {
            "download_links": [
                {c.name: getattr(link, c.name) for c in DownloadLink.__table__.columns} 
                for link in links
            ],
            "scraped_urls": [
                {c.name: getattr(url, c.name) for c in ScrapedURL.__table__.columns}
                for url in scraped
            ],
            "backup_date": datetime.now().isoformat()
        }
        
        # Write to JSON
        backup_path = "data/backup.json"
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, default=json_serial, ensure_ascii=False)
            
        print(f"SUCCESS: Exported {len(links)} links and {len(scraped)} history entries.")
        print(f"File saved to: {backup_path}")

if __name__ == "__main__":
    asyncio.run(backup())
