# Cloudflare Bypass & Configuration

To unlock links protected by Cloudflare Turnstile, DDLtower uses a remote-controlled browser within the `webtop` container.

## `socat` Installation

`socat` is required to bridge the network between the `ddltower` container and the browser.
Install it manually inside the container:
```bash
sudo docker exec -it ddltower-browser apt-get update
sudo docker exec -it ddltower-browser apt-get install -y socat
```

## Development environment

To launch the development environment:
```bash
docker compose -f docker-compose.dev.yml up -d
```

## Environment Variables (.env)

The `.env` file is used to manage permissions for the non-root user and allow access to the Docker socket:

- `UID`: Your local user ID (default: 1000)
- `GID`: Your local group ID (default: 1000)
- `DOCKER_GID`: The GID of the `docker` group on your host (needed for Link Unlocking).
- `NODE_NO_WARNINGS`: Suppress Node.js warnings (default: 1)

You can generate it automatically with:
```bash
echo -e "UID=$(id -u)\nGID=$(id -g)\nDOCKER_GID=$(getent group docker | cut -d: -f3)\nNODE_NO_WARNINGS=1" > .env
```

## Application Settings

Settings are managed in `config/config.yaml`.
