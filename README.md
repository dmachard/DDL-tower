# DDLtower

DDLtower is a automation tool for web link extraction, tagging and management.

* This project is a vibe coding project with Antigravity.

## Features

- **Quick-Scan**: Instant URL extraction via headless browser.
- **Tagging**: Metadata fetching via **TMDb** with automatic translation for plots and posters.
- **Ratings**: Visual rating scale (1-10) integrated into the dashboard.
- **Categorization**: Intelligent filename parsing (PTN) for quality, language, and season/episode detection.
- **Stats Dashboard**: Complete overview of library volume and health.

## Getting Started

```bash
git clone https://github.com/dmachard/ddltower.git
cd ddl-tower
mkdir data/
docker compose up -d
```

**Dashboard**: [http://localhost:8001](http://localhost:8001)

### Development environment

To launch the development environment:
```bash
docker compose -f docker-compose.dev.yml up -d
```

## Configuration

Settings are managed in `config/config.yaml`.

## Maintenance CLI

DDLtower provides a unified command-line tool for administrative and maintenance tasks.

### Database Management (`db`)
Manage your library integrity and backups:
```bash
# Backup/Restore
docker compose exec ddltower python3 -m app.cli.main db backup
docker compose exec ddltower python3 -m app.cli.main db restore

# Manually rename or fix an entry by Title or ID
docker compose exec ddltower python3 -m app.cli.main db update-title --title "Old Title" --new-title "New Title"
docker compose exec ddltower python3 -m app.cli.main db update-title --id 123 --new-title "New Title"

# Clear scraping history (all or by pattern)
docker compose exec ddltower python3 -m app.cli.main db reset-scans --pattern "example.com"

# Clear metadata for re-tagging (specific title)
docker compose exec ddltower python3 -m app.cli.main db reset-metadata --title "Inception"

# WIPE ALL metadata (start fresh with new TMDb priority)
docker compose exec ddltower python3 -m app.cli.main db reset-all

# Comprehensive cleanup and health audit
docker compose exec ddltower python3 -m app.cli.main db cleanup
docker compose exec ddltower python3 -m app.cli.main db audit
```

### Metadata Tagging (`tag`)
Match links with external metadata:
```bash
# [NEW] Simplified re-tagging (Rename + Search + Tag in one go)
docker compose exec ddltower python3 -m app.cli.main tag --title "Old Title" --rename-to "New Title" --year 2024

# Batch tagging (unenriched links)
docker compose exec ddltower python3 -m app.cli.main tag --limit 300

# Force specific match by title/year or IMDb ID
docker compose exec ddltower python3 -m app.cli.main tag --title "Inception" --year 2010
docker compose exec ddltower python3 -m app.cli.main tag --title "Deadpool" --id tt0439572

# Repair missing data (Missing posters or 404s)
docker compose exec ddltower python3 -m app.cli.main tag --repair
```

### Link Management (`links`)

```bash
# View detailed records for an item
docker compose exec ddltower python3 -m app.cli.main links view "Deadpool"

# Re-verify all links currently marked as 'dead'
docker compose exec ddltower python3 -m app.cli.main links reverify

### Scraper Management (`scan`)
Trigger scraping manually:

```bash
# Manually trigger a full scan of all configured sources (RSS & Crawl)
docker compose exec ddltower python3 -m app.cli.main scan
```

### Sqlite

```bash
sudo docker compose exec ddltower sqlite3 /app/data/ddl.db "SELECT official_title, poster_path, year FROM media_metadata WHERE imdb_id='tt32430579';"
```

