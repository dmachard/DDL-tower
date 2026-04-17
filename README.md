# DDLtower

> This project is a vibe coding project with Antigravity.

DDLtower is a automation tool for web link extraction, tagging and management.

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
# Create .env file with your IDs
echo -e "UID=$(id -u)\nGID=$(id -g)\nDOCKER_GID=$(getent group docker | cut -d: -f3)" > .env
docker compose up -d
```

**Dashboard**: [http://localhost:8001](http://localhost:8001)

## Cloudflare Bypass (Turnstile)

To unlock links protected by Cloudflare Turnstile, DDLtower uses a remote-controlled browser within the `webtop` container.

### `socat` Installation

`socat` is required to bridge the network between the `ddltower` container and the browser.
Install it manually inside the container:
```bash
docker exec -it ddltower-browser apt-get update
docker exec -it ddltower-browser apt-get install -y socat
```

### Development environment

To launch the development environment:
```bash
docker compose -f docker-compose.dev.yml up -d
```

### Environment Variables (.env)

The `.env` file is used to manage permissions for the non-root user and allow access to the Docker socket:

- `UID`: Your local user ID (default: 1000)
- `GID`: Your local group ID (default: 1000)
- `DOCKER_GID`: The GID of the `docker` group on your host (needed for Link Unlocking).

You can generate it automatically with:
```bash
echo -e "UID=$(id -u)\nGID=$(id -g)\nDOCKER_GID=$(getent group docker | cut -d: -f3)" > .env
```

### Application Settings

Settings are managed in `config/config.yaml`.

## Maintenance CLI

DDLtower provides a unified command-line tool for administrative and maintenance tasks.

### Database Management (`db`)
Manage your library integrity and backups:
```bash
# Backup/Restore
sudo docker compose exec ddltower python3 -m app.cli.main db backup
sudo docker compose exec ddltower python3 -m app.cli.main db restore

# Manually rename or fix an entry by Title or ID
sudo docker compose exec ddltower python3 -m app.cli.main db update-title --title "Old Title" --new-title "New Title"
sudo docker compose exec ddltower python3 -m app.cli.main db update-title --id 123 --new-title "New Title"

# Clear scraping history (all or by pattern)
sudo docker compose exec ddltower python3 -m app.cli.main db reset-scans --pattern "example.com"

# Clear metadata for re-tagging (specific title)
sudo docker compose exec ddltower python3 -m app.cli.main db reset-metadata --title "Inception"

# WIPE ALL metadata (start fresh with new TMDb priority)
sudo docker compose exec ddltower python3 -m app.cli.main db reset-all

# Comprehensive cleanup and health audit
sudo docker compose exec ddltower python3 -m app.cli.main db cleanup
sudo docker compose exec ddltower python3 -m app.cli.main db audit
```

### Metadata Tagging (`tag`)
Match links with external metadata:
```bash
# [NEW] Simplified re-tagging (Rename + Search + Tag in one go)
sudo docker compose exec ddltower python3 -m app.cli.main tag --title "Old Title" --rename-to "New Title" --year 2024

# Batch tagging (unenriched links)
sudo docker compose exec ddltower python3 -m app.cli.main tag --limit 300

# Force specific match by title/year or IMDb ID
sudo docker compose exec ddltower python3 -m app.cli.main tag --title "Inception" --year 2010
sudo docker compose exec ddltower python3 -m app.cli.main tag --title "Deadpool" --id tt0439572

# Repair missing data (Missing posters or 404s)
sudo docker compose exec ddltower python3 -m app.cli.main tag --repair
```

### Link Management (`links`)

```bash
# View detailed records for an item
sudo docker compose exec ddltower python3 -m app.cli.main links view "Deadpool"

# Re-verify all links currently marked as 'dead'
sudo docker compose exec ddltower python3 -m app.cli.main links reverify

### Scraper Management (`scan`)
Trigger scraping manually:

```bash
# Manually trigger a full scan of all configured sources (RSS & Crawl)
sudo docker compose exec ddltower python3 -m app.cli.main scan
```


### Sqlite

```bash
sudo docker compose exec ddltower sqlite3 /app/data/ddl.db "SELECT official_title, poster_path, year FROM media_metadata WHERE imdb_id='tt32430579';"

sudo docker compose exec ddltower sqlite3 ./data/ddl.db "DELETE FROM download_links; DELETE FROM scraped_urls;"

```

