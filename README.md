# DDLtower 🚀

DDLtower is a high-performance automation tool for link extraction, enrichment, and management with a real-time, premium dashboard.

## ✨ Features

- **Quick-Scan**: Instant URL extraction via headless browser.
- **OMDb Enrichment**: Automatic fetching of posters (local copy), plots, and official titles.
- **Categorization**: Intelligent filename parsing (PTN) for quality, language, and season/episode detection.
- **Stats Dashboard**: Complete overview of library volume and health.
- **I18n**: Full support for English and French.

## 🚀 Getting Started

```bash
git clone https://github.com/dmachard/ddltower.git
cd ddl-tower
docker compose up -d
```

**Dashboard**: [http://localhost:8001](http://localhost:8001)

## ⚙️ Configuration

Settings are managed in `config/config.yaml`.

### OMDb Integration (Optional)
To enable posters and plots, add your [OMDb API Key](http://www.omdbapi.com/apikey.aspx):
```yaml
omdb:
  api_key: "your_key_here"
  language: "fr" # Results language
```

## 🛠️ CLI Utilities (Scripts)

You can run these utilities via `docker compose exec`.

### 🔍 Manual Enrichment (Categorization)
Trigger a full OMDb and PTN enrichment for a specific title or all links matching a name:
```bash
docker compose exec app python3 -m app.scripts.enrich_by_title "Deadpool"
```

### 📦 View Database Content (Raw)
Dump all database columns and values for a specific title (JSON-like raw output):
```bash
docker compose exec app python3 -m app.scripts.view_item "Country Comfort"
```

### ♻️ Reset Scans
Clear the "scanned" status of one or all URLs to force a fresh scrape:
```bash
# Reset a specific URL
docker compose exec app python3 -m app.scripts.reset_links "http://example.com/page"
# Reset ALL URLs
docker compose exec app python3 -m app.scripts.reset_links
```

### 💀 Re-verify Dead Links
Manually trigger a health check for all links currently marked as dead:
```bash
docker compose exec app python3 -m app.scripts.reverify_dead
```

### 💾 Backup & Restore
Maintain your database:
```bash
# Backup to ./data/backups/
docker compose exec app python3 -m app.scripts.backup
# Restore from latest backup
docker compose exec app python3 -m app.scripts.restore
```

## 🏗️ Tech Stack
- **Backend**: FastAPI (Python), SQLAlchemy, SQLite (WAL mode).
- **Frontend**: Vanilla JS/CSS, Glassmorphism design, Outfit font.
- **Extraction**: Headless browser, PTN, OMDb API.