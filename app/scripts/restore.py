import asyncio
import json
import os
import sys
from datetime import datetime

# Add the project root to sys.path to allow imports from "app"
sys.path.append(os.getcwd())

from app.db.database import AsyncSessionLocal
from app.db.models import DownloadLink, ScrapedURL

async def restore():
    print("--- DDLtower Restore Utility ---")
    backup_path = "data/backup.json"
    
    if not os.path.exists(backup_path):
        print(f"ERROR: Backup file {backup_path} not found.")
        return

    with open(backup_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    def parse_dt(s):
        if not s: return None
        return datetime.fromisoformat(s.replace('Z', '+00:00'))

    async with AsyncSessionLocal() as session:
        # 1. Restore Scraped URLs
        scraped_count = 0
        for entry_data in data.get("scraped_urls", []):
            # Convert ISO dates back to datetime objects
            if "last_scraped" in entry_data and entry_data["last_scraped"]:
                entry_data["last_scraped"] = parse_dt(entry_data["last_scraped"])
            
            # Use merge to avoid duplicates/errors
            # Filter keys to only those that exist in the current model (SHEMA RESILIENCE)
            model_keys = {c.name for c in ScrapedURL.__table__.columns}
            filtered_data = {k: v for k, v in entry_data.items() if k in model_keys}
            
            obj = ScrapedURL(**filtered_data)
            await session.merge(obj)
            scraped_count += 1
            
        # 2. Restore Download Links
        links_count = 0
        for link_data in data.get("download_links", []):
            if "last_checked" in link_data and link_data["last_checked"]:
                link_data["last_checked"] = parse_dt(link_data["last_checked"])
            
            # Filter keys to only those that exist in the current model (SHEMA RESILIENCE)
            model_keys = {c.name for c in DownloadLink.__table__.columns}
            filtered_data = {k: v for k, v in link_data.items() if k in model_keys}
            
            # We skip 'id' during restore to let SQLite assign new ones 
            # OR keep them if we want to preserve relational integrity.
            # Here, we keep 'id' for merge consistency.
            obj = DownloadLink(**filtered_data)
            await session.merge(obj)
            links_count += 1

        await session.commit()
        print(f"SUCCESS: Restored {links_count} links and {scraped_count} history entries.")

if __name__ == "__main__":
    asyncio.run(restore())
