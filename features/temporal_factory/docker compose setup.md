# docker compose setup

Source of truth: `docker-compose.yml` (repo root).

## initial vibe setup

| Service | Image | Notes |
|---|---|---|
| `postgres` | `postgres:19` in the file (the running container was `postgres:16`) | User/password `temporal`; volume `pg-data` at `/var/lib/postgresql/data`. No healthcheck. |
| `temporal` | `temporalio/auto-setup:1.25.2` | Created the schemas and the `default` namespace itself. `DB=postgres12`, `POSTGRES_SEEDS=postgres`; port 7233. |
| `temporal-ui` | `temporalio/ui:2.31.2` | `TEMPORAL_ADDRESS=temporal:7233`; port 8080. |
| `worker` | built from `Dockerfile` | `restart: on-failure`, `env_file: .env`, volume `factory-data` at `/data`. |

- Startup order came from plain `depends_on` lists, with no health conditions.
- Volumes: `pg-data`, `factory-data`.
- Fix after setup: UI bumped from `2.31.2` to `2.58.1`. In Chrome, the old UI's Content Security Policy blocked its own scripts, so the page rendered blank.

## 2nd revision

| Service | Image | Notes |
|---|---|---|
| `postgres` | `postgres:19` | Volume `pg-data` now mounted at `/var/lib/postgresql` (Postgres 18+ layout). Healthcheck: `pg_isready -U temporal`. |
| `temporal-schema` | `temporalio/admin-tools:1.32.2` | Runs once, after `postgres` is healthy; `restart: on-failure:6`. Uses `temporal-sql-tool` (plugin `postgres12`) to run `create-database`, `setup-schema -v 0.0` and `update-schema` for the `temporal` and `temporal_visibility` databases, from `/etc/temporal/schema/postgresql/v12/{temporal,visibility}/versioned`. |
| `temporal` | `temporalio/server:1.32.2` | Replaces `auto-setup`. Starts after `temporal-schema` completes successfully. Env: `DB=postgres12`, `DB_PORT=5432`, `POSTGRES_USER`/`POSTGRES_PWD=temporal`, `POSTGRES_SEEDS=postgres`, `BIND_ON_IP=0.0.0.0`, `DYNAMIC_CONFIG_FILE_PATH=config/dynamicconfig/development.yaml`. Mounts `./temporal/dynamicconfig` at `/etc/temporal/config/dynamicconfig`. Port 7233. Healthcheck: `nc -z localhost 7233`. |
| `temporal-namespace` | `temporalio/admin-tools:1.32.2` | Runs once, after `temporal` is healthy; `restart: on-failure:5`. Creates the `default` namespace if it doesn't exist (`temporal operator namespace describe … \|\| … create`). |
| `temporal-ui` | `temporalio/ui:2.58.1` | Starts after `temporal` is healthy. Port 8080. |
| `worker` | built from `Dockerfile` | Starts after `temporal-namespace` completes successfully. Otherwise unchanged. |

- New file `temporal/dynamicconfig/development.yaml` sets `system.forceSearchAttributesCacheRefreshOnRead: true`.
- Volumes:
  - `pg-data` is now named `temporal_factory_pg19-data`, a fresh volume.
  - The old Postgres 16 data is still in `temporal_factory_pg-data` and is not used.
  - `factory-data` is unchanged.
- Elasticsearch is not used, unlike the compose example in Temporal's docs. Visibility data is stored in Postgres.
