# Setup

Use the commands in the root README for the shortest path. Python 3.12 and Node 24 are the tested language targets. `requirements.lock` and `package-lock.json` pin the tested dependency graph.

## Environment separation

Use different databases, object containers, OAuth apps and Stripe modes for demo, development, staging and production. Never seed a real tenant. `realty.seed` refuses non-demo or production execution and is idempotent by demo account identity. Creating a new account starts an empty organization.

For PostgreSQL locally, start `docker compose up db -d` and configure `DATABASE_URL=postgresql+psycopg://realty:local-development-only@localhost:5432/realty`. Run migrations before starting the app. This Compose password is a development fixture, not a deployable secret.

For ordinary development use Vite on localhost:5173 and the API on localhost:8000 with `APP_ORIGIN=http://localhost:5173`. For production-asset preview use `APP_ORIGIN=http://localhost:8000`, build, and start the API; it serves `dist/` only when built assets exist at startup. Origin matching is exact: use `localhost` consistently rather than switching to `127.0.0.1` in browser URLs.

The API and worker must both run for approved jobs to execute. The worker performs an hourly sweep and polls queued work every two seconds. Use Settings → Activity to inspect attempts and errors. API docs are available at `/api/docs` outside production.

## Windows restricted-host note

This build host required a workspace-local package cache and inherited ACLs for Python temporary directories. The repository itself does not require a custom Python runtime. Standard installation is preferred outside that host. If an npm wrapper cannot spawn its shell, invoke `node scripts/build.mjs` directly. If Vite cannot create its esbuild IPC pipes, use the built application served by FastAPI.

## Clean recovery

Back up valuable data first. To start a completely separate demo, set a new SQLite database filename and rerun migrations/seed. Do not delete the existing database merely to apply a schema change. Production migrations are a separate controlled release step.
