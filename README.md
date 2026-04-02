# DDL-tower

DDLtower is a tool to automate link extraction, categorization and management from web sources via a headless browser engine with a real-time dashboard.

## Features

- Quick-Scan: Paste any URL for immediate extraction.
- Metadata Extraction: Parses filenames to extract size, name, etc.
- Stats Dashboard: Monitor indexed volume and category distribution.

## Getting Started

```bash
git clone https://github.com/dmachard/ddltower.git
cd ddltower
docker compose up -d

Dashboard : http://localhost:8001

## Configuration

Via config/config.yaml — scanning patterns, scheduler frequency, integrations.