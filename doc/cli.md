# Maintenance CLI

DDLtower provides a unified command-line tool for administrative and maintenance tasks.

## Database Management (`db`)
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

# WIPE ALL
sudo docker compose exec ddltower python3 -m app.cli.main db wipe

# Comprehensive cleanup and health audit
sudo docker compose exec ddltower python3 -m app.cli.main db cleanup
sudo docker compose exec ddltower python3 -m app.cli.main db audit
```

## Metadata Tagging (`tag`)
Match links with external metadata:
```bash
# [NEW] Simplified re-tagging (Rename + Search + Tag in one go)
sudo docker compose exec ddltower python3 -m app.cli.main tag --title "Old Title" --rename-to "New Title" --year 2024

# Batch tagging (unenriched links)
sudo docker compose exec ddltower python3 -m app.cli.main tag --limit 300

# Force specific match by title/year or IMDb ID
sudo docker compose exec ddltower python3 -m app.cli.main tag --title "Inception" --year 2010
sudo docker compose exec ddltower python3 -m app.cli.main tag --title "Deadpool" --id tt0439572

# Repair missing data (Missing posters, 404s, OR incorrectly grouped multi-part releases)
sudo docker compose exec ddltower python3 -m app.cli.main tag --repair
```

## Link Management (`links`)

```bash
# View detailed records for an item
sudo docker compose exec ddltower python3 -m app.cli.main links view "Deadpool"

# Re-verify all links currently marked as 'dead'
sudo docker compose exec ddltower python3 -m app.cli.main links reverify

# Re-tag a specific title
sudo docker compose exec ddltower python3 -m app.cli.main tag --title "CptinCurgos19770BuayFA20x6PTr%" --rename-to "Captains Courageous"  --year 1937
```

## Scraper Management (`scan`)
Trigger scraping manually:

```bash
sudo docker compose exec ddltower python3 -m app.cli.main scan

# Manually trigger a full scan of all configured sources (RSS & Crawl)
sudo docker compose exec ddltower python3 -m app.cli.main scan --source "MySource"
```

## Browser Management (`browser`)
Control the headless browser instance:
```bash
# Force a clean restart of the Chromium instance (useful if Cloudflare/Playwright hangs)
sudo docker compose exec ddltower curl -X POST http://localhost:8001/api/browser/restart
```

## Database Export & Git Synchronization (`export`)
Export releases database and stats for static dashboard rendering:
```bash
# Export both data.db.gz and stats.db.gz to configured data_export_dir
sudo docker compose exec ddltower python3 -m app.cli.main export

# Export only data (data.db.gz) or only stats (stats.db.gz)
sudo docker compose exec ddltower python3 -m app.cli.main export --type data
sudo docker compose exec ddltower python3 -m app.cli.main export --type stats

# Specify a custom local output folder (overriding the configuration file)
sudo docker compose exec ddltower python3 -m app.cli.main export --output-dir /app/data/custom_export

# Parse and merge external input files (JSON or text-based line releases)
sudo docker compose exec ddltower python3 -m app.cli.main export --input /app/data/my_releases.json
```

If Git synchronization is enabled in your `config.yaml` (`git.enabled: true`), the exported files will be committed and pushed to the configured repository and branch automatically. If the branch does not exist on the remote repository yet, DDLtower will automatically create and publish it.

### Automatic Exporting after Scraping

You can configure DDLtower to automatically run the export process (and sync to Git if enabled) immediately after scrapers finish running. This is configured in `config.yaml`:

```yaml
# Auto Export Settings (after scrapers finish running)
auto_export:
  enabled: true # Enable/disable auto-export
  type: "all"   # Options: "all", "data", "stats"
```

## Sqlite

```bash
sudo docker compose exec ddltower sqlite3 /app/data/ddl.db "SELECT official_title, poster_path, year FROM media_metadata WHERE imdb_id='tt32430579';"

sudo docker compose exec ddltower sqlite3 ./data/ddl.db "DELETE FROM download_links; DELETE FROM scraped_urls;"
```
