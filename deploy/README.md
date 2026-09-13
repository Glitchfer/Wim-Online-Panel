# deploy/ — Deployment configuration for WIM Online

Containerized, isolated deployment of the WIM Online SFA platform.

## Services

| Service | Image | Runs | Notes |
|---------|-------|------|-------|
| wim-db | postgres:17-alpine | PostgreSQL 17 (schema in `db/init/`) | Data persists in `pgdata` volume |
| wim-api | python:3.13-slim | serve.py (API/middleware only) | psycopg2 → wim-db |
| sales-app | nginx:alpine | static frontend + /api proxy | template injects API_HOST/PORT |
| admin-panel | python:3.13-slim | admin-server.py | **must migrate to PG first** |

## Usage

```bash
cp env/.env.example .env        # fill real values
docker compose up -d --build
docker compose ps
docker compose logs -f wim-api
```

## Layout

```
deploy/
├── docker-compose.yml
├── env/.env.example
├── api/          → Dockerfile, requirements.txt, serve.py
├── sales-app/    → Dockerfile, nginx.conf, www/ (static files)
├── admin/        → Dockerfile, requirements.txt, admin-server.py
└── db/init/      → 01-schema.sql, 02-seed.sql
```

## Notes
- **admin-server.py is still on MySQL/pymysql → fleetbase.** It must be migrated to
  psycopg2/wim_sfa before the admin-panel container is built (see DEPLOYMENT.md §15).
- Copy the real `frontend/` static files into `sales-app/www/` before building.
- Secrets live in `.env` (gitignored), never in images or git.