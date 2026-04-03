import sqlite3
import os
import sys

# Database path inside the container
DB_PATH = "/app/data/ddl.db"

def reset_scraped_urls(pattern=None):
    if not os.path.exists(DB_PATH):
        # Fallback for local execution
        local_db = "./data/ddl.db"
        if os.path.exists(local_db):
            db = local_db
        else:
            print(f"Error: Database not found at {DB_PATH} or {local_db}")
            return
    else:
        db = DB_PATH

    try:
        conn = sqlite3.connect(db)
        cursor = conn.cursor()

        if pattern:
            print(f"Cleaning scraping history for pattern: {pattern}...")
            cursor.execute("DELETE FROM scraped_urls WHERE url LIKE ?", (f"%{pattern}%",))
        else:
            print("Cleaning ALL scraping history...")
            cursor.execute("DELETE FROM scraped_urls")

        conn.commit()
        count = conn.total_changes
        conn.close()
        print(f"Success: {count} entries removed. You can now trigger a new scan.")
    except Exception as e:
        print(f"Database error: {e}")

if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else None
    reset_scraped_urls(p)
