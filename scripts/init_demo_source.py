"""Idempotent script to seed Demo-Source with sample movies and series."""
import argparse
import os
import sqlite3
from datetime import datetime, timedelta, timezone

from app.core.config import settings

DEMO_MOVIES = [
    ("tt9000001", "Dune: Part Two", 2024, "8.5", "Paul Atreides unites with the Fremen."),
    ("tt9000002", "Blade Runner 2049", 2017, "8.0", "A young blade runner discovers a long-buried secret."),
    ("tt9000003", "Interstellar", 2014, "8.7", "A team of explorers travel through a wormhole in space."),
    ("tt9000004", "Mad Max: Fury Road", 2015, "8.1", "In a post-apocalyptic wasteland, Max teams up with Furiosa."),
]

DEMO_SERIES = [
    ("tt9000005", "Severance", 2022, "8.7", "Mark leads a team of office workers whose memories have been surgically divided."),
    ("tt9000006", "Andor", 2022, "8.4", "Prequel series to Rogue One following Cassian Andor."),
    ("tt9000007", "The Last of Us", 2023, "8.8", "Joel and Ellie survive across a post-pandemic America."),
    ("tt9000008", "Dark", 2017, "8.7", "A family saga with a supernatural twist set in a German town."),
]


def seed_demo_source(force: bool = False) -> int:
    db_path = settings.DATABASE_URL.split(":///")[-1]
    poster_dir = settings.POSTER_DIR
    posters = (
        sorted(f for f in os.listdir(poster_dir) if f.endswith(".jpg") and not f.startswith("."))
        if os.path.isdir(poster_dir)
        else []
    )

    conn = sqlite3.connect(db_path)
    try:
        existing = conn.execute(
            "SELECT COUNT(*) FROM download_links WHERE source_name = 'Demo-Source'"
        ).fetchone()[0]
        if existing > 0 and not force:
            print(f"Demo-Source already exists ({existing} links), skipping.")
            return 0

        if force and existing > 0:
            conn.execute("DELETE FROM download_links WHERE source_name = 'Demo-Source'")

        now = datetime.now(timezone.utc)
        now_s = now.strftime("%Y-%m-%d %H:%M:%S")
        old_s = (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")

        for idx, (imdb, title, year, rating, plot) in enumerate(DEMO_MOVIES + DEMO_SERIES):
            poster = posters[idx % len(posters)] if posters else None
            conn.execute(
                """INSERT OR REPLACE INTO media_metadata
                   (imdb_id, official_title, title_fr, year, poster_path, plot_en, plot_fr, rating)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (imdb, title, title, year, poster, plot, plot, rating),
            )

        inserted = 0
        for idx, (imdb, title, year, _, _) in enumerate(DEMO_MOVIES):
            for j, res in enumerate(("2160p", "1080p")):
                ts = now_s if (idx < 3 and j == 0) else old_s
                conn.execute(
                    """INSERT OR REPLACE INTO download_links
                       (url, hoster, status, filename, size, size_bytes, last_checked, created_at,
                        source_name, title, category, year, resolution, quality, codec, language, imdb_id)
                       VALUES (?, '1fichier', 'alive', ?, '8.4 GB', 8400000000, ?, ?,
                               'Demo-Source', ?, 'movie', ?, ?, 'WEB-DL', 'H.265', 'MULTI', ?)""",
                    (f"https://1fichier.com/?demo_m_{idx}_{j}", f"{title}.{year}.{res}.mkv", ts, ts, title, year, res, imdb),
                )
                inserted += 1

        for idx, (imdb, title, year, _, _) in enumerate(DEMO_SERIES):
            for ep in range(1, 4):
                ts = now_s if (idx < 2 and ep <= 2) else old_s
                conn.execute(
                    """INSERT OR REPLACE INTO download_links
                       (url, hoster, status, filename, size, size_bytes, last_checked, created_at,
                        source_name, title, category, year, season, episode, resolution, quality, codec, language, imdb_id)
                       VALUES (?, '1fichier', 'alive', ?, '2.1 GB', 2100000000, ?, ?,
                               'Demo-Source', ?, 'series', ?, '1', ?, '1080p', 'WEBRIP', 'H.265', 'MULTI', ?)""",
                    (f"https://1fichier.com/?demo_s_{idx}_{ep}", f"{title}.S01E0{ep}.1080p.mkv", ts, ts, title, year, str(ep), imdb),
                )
                inserted += 1

        conn.commit()
        print(f"Seeded Demo-Source ({inserted} links, {len(posters)} posters available).")
        return inserted
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed Demo-Source if missing.")
    parser.add_argument("--force", action="store_true", help="Recreate Demo-Source even if it already exists.")
    args = parser.parse_args()
    seed_demo_source(force=args.force)

