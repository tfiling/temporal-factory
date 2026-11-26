---
type: known-limitation
status: open
created: 2026-11-26
tags: [docker, compose, postgres]
---

# Shared postgres volume name

`docker-compose.yml` pins `name: temporal_factory_pg-data`, so a second Compose project (`-p`, `COMPOSE_PROJECT_NAME`, a differently named checkout) mounts the **same** database. If both run, two Postgres servers write one data directory and can corrupt it; Postgres' lock file does not stop this across containers. Compose only prints an "already exists but was created for project" warning.

Seen 2026-11-26 while testing in an isolated project (about 2 minutes of overlap).

Until fixed: never start a second project from this compose file without overriding the volume.
