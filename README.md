# DDLtower

DDLtower is an automation tool for web link extraction, tagging, and management.

<p align="center">
  <img src="doc/log_ddltower.png" alt="DDLtower Logo" width="200">
</p>

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

### Generic Hosters (`config.yaml`)

HTTP-based hoster checks can be configured declaratively under `hosters:` in `config/config.yaml` (specialized Python services like `1fichier.com`, `turbobit.net`, `dailyuploads.net`, and `youtube.com` remain built-in unless overridden):

```yaml
hosters:
  - name: "rapidgator"
    domains: ["rapidgator.net"]
    allow_redirects: false
    dead_if_status: [301, 302, 303, 307, 308, 404]
    dead_if_text: ["404 File not found", "Page not found"]
    error_if_text: ["challenges.cloudflare.com", "turnstile"]
    alive_if_text: ["File size:"]
    extract-filename_regex: 'Downloading:.*?<a[^>]*>([^<]+)</a>'
    extract-size_regex: 'File size:.*?<strong>([^<]+)</strong>'
```

## For developers

Running tests

```bash
docker compose exec -T ddltower python3 -m pytest -p no:cacheprovider -v app/tests/test*
```

Seed demo source (`Demo-Source`, idempotent, pass `--force` to recreate):

```bash
docker compose exec -T ddltower python3 - < scripts/init_demo_source.py
```