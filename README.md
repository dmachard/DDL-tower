# DDLtower

DDLtower is an automation tool for web link extraction, tagging, and management.

## Features

- **Quick-Scan**: Instant URL extraction via headless browser.
- **Tagging**: Metadata fetching via **TMDb** with automatic translation for plots and posters.
- **Stats Dashboard**: Complete overview of library volume and health.
- **Embedded Browser**: Dedicated Chromium instance via **Webtop** for manual navigation.
- **RSS**: Generate **RSS 2.0** feeds for both latest discovered releases and completed download history.
- **Git Database Export**: Auto-export stats and data to a remote Git repository

## Getting Started

```bash
git clone https://github.com/dmachard/ddl-tower.git
cd ddl-tower
mkdir data/
# Create .env file with your IDs
echo -e "UID=$(id -u)\nGID=$(id -g)\nDOCKER_GID=$(getent group docker | cut -d: -f3)\nNODE_NO_WARNINGS=1" > .env
docker compose up -d
```
### Quick Links

| Service | URL | Description |
| :--- | :--- | :--- |
| **Dashboard** | [http://localhost:8001](http://localhost:8001) | Main user interface |
| **Browser (Webtop)** | [http://localhost:8002](http://localhost:8002) | Integrated Chromium browser |


## Documentation

To keep this main README simple, all detailed documentation has been moved to the `doc/` directory:

- �️ **[Maintenance CLI](doc/cli.md)**: Database commands, manual tagging, browser restarts.
- 🕷️ **[Universal Scraper](doc/scraper.md)**: How to configure complex scrapers, chaining, unlockers, and templates.
- 📖 **[Browser Config](doc/browser.md)**: Setup socat, webtop, and `.env`.
- 📐 **[Architecture](doc/architecture.md)**: Flowcharts of the discovery, tagging, and downloading pipeline.
- 📡 **[RSS Feeds](doc/rss.md)**: Feed endpoints, query filters, and categories.

## For developers

Running tests

```bash
docker compose exec -T ddltower python3 -m pytest -p no:cacheprovider -v app/tests/test*
```