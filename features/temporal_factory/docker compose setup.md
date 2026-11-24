# docker compose setup

Source of truth: `docker-compose.yml` (repo root).

## Current setup

| Service | Image | Notes |
|---|---|---|
| `postgres` | `postgres:19` | Volume `pg-data` mounted at `/var/lib/postgresql` (Postgres 18+ layout). Healthcheck: `pg_isready -U temporal`. |
| `temporal-schema` | `temporalio/admin-tools:1.32.2` | Runs once, after `postgres` is healthy; `restart: on-failure:6`. Uses `temporal-sql-tool` (`--plugin postgres12`, the plugin name, not a Postgres version) to run `create-database`, `setup-schema -v 0.0` and `update-schema` for the `temporal` and `temporal_visibility` databases, from `/etc/temporal/schema/postgresql/v12/{temporal,visibility}/versioned` (`v12` is the schema directory name in the admin-tools image, not a Postgres version). Errors from `create-database` and `setup-schema` are swallowed (`2>/dev/null \|\| true`); only `update-schema` can fail the job. |
| `temporal` | `temporalio/server:1.32.2` | Starts after `temporal-schema` completes successfully. Env: `DB=postgres12` (Temporal's Postgres persistence plugin name, not the Postgres version; the database is Postgres 19), `DB_PORT=5432`, `POSTGRES_USER=temporal` and `POSTGRES_PWD=temporal` (the Temporal server's variable; the `postgres` service uses `POSTGRES_PASSWORD`), `POSTGRES_SEEDS=postgres`, `BIND_ON_IP=0.0.0.0`, `DYNAMIC_CONFIG_FILE_PATH=config/dynamicconfig/development.yaml`. Mounts `./temporal/dynamicconfig` at `/etc/temporal/config/dynamicconfig`. Port 7233. Healthcheck: `nc -z localhost 7233`. |
| `temporal-namespace` | `temporalio/admin-tools:1.32.2` | Runs once, after `temporal` is healthy; `restart: on-failure:5`. Creates the `default` namespace if it doesn't exist (`temporal operator namespace describe … \|\| … create`). |
| `temporal-ui` | `temporalio/ui:2.58.1` | Starts after `temporal` is healthy. Port 8080. |
| `worker` | built from `Dockerfile` | Starts after `temporal-namespace` completes successfully. `restart: on-failure`, `env_file: .env`, env `TEMPORAL_ADDRESS=temporal:7233`, volume `factory-data` at `/data`. |

- `temporal/dynamicconfig/development.yaml` sets `system.forceSearchAttributesCacheRefreshOnRead: true`.
- Volumes:
  - `pg-data` is pinned to the explicit name `temporal_factory_pg-data` (the same name Compose generates by default for this project) and mounted at `/var/lib/postgresql`. It was recreated empty and holds only Postgres 19 data.
  - `factory-data`: definition unchanged (`factory-data:/data` on the worker); recreated empty with the stack.
- Elasticsearch is not used, unlike the compose example in Temporal's docs. Visibility data is stored in Postgres.
