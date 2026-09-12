# RealtyAI

**The AI handles the busywork. The realtor handles the relationship.**

RealtyAI is a modular real-estate CRM with a working API, relational database, background worker, React workspace and approval-driven intelligence. It runs locally without production credentials in an explicitly labelled demo workspace.

This is a tested foundation, **not a certified production release**. Live Google/Stripe/OpenAI validation, browser acceptance, PostgreSQL deployment validation and cloud rollout have separate acceptance gates. See [acceptance and limitations](docs/acceptance.md).

## Start locally

Prerequisites: Python 3.12+, Node.js 24 LTS, Git. Docker is optional.

```sh
git clone --branch feat/realtyai-foundation https://github.com/DropBen/realty-ai-platform.git
cd realty-ai-platform
python -m venv .venv
```

Activate with `.venv\Scripts\Activate.ps1` on Windows or `source .venv/bin/activate` on macOS/Linux.

```sh
pip install -r requirements.lock
pip install -e . --no-deps --no-build-isolation
npm ci
```

Copy `.env.example` to `.env`. For a single-origin local build, set `APP_ORIGIN=http://localhost:8000` in `.env`.

```sh
python -m alembic upgrade head
python -m realty.seed
npm run build
python -m uvicorn realty.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

In a second activated terminal:

```sh
python -m realty.jobs
```

Open **http://localhost:8000** and choose **Explore demo workspace**. Demo credentials: `sarah@realty.example.com` / `RealtyAI-demo-2026!`. Seed records are fictional, and demo mode refuses external Google, AI and Stripe operations. Keep its database separate from real data.

For frontend hot reload, set `APP_ORIGIN=http://localhost:5173`, run the API on port 8000 and `npm run dev`, then open **http://localhost:5173**. The Vite proxy keeps requests on the browser's origin. Restart the API after configuration changes.

With Docker running, `docker compose up --build` starts PostgreSQL, migrations, demo seed, application and worker in order. Docker configuration is intended for local development.

## What works

- Password authentication, server sessions, CSRF, five roles, organization memberships and organization switching.
- Contacts/leads/buyers/sellers, confirmed preferences, source facts, a relationship timeline, notes/calls/showing feedback, properties, deals and transaction milestones.
- Tasks, local appointments, calendar conflict detection, available-time suggestions and meeting preparation.
- Data-derived briefing, bounded natural-language search, explainable buyer/property matching, email extraction, proposed commitments and follow-up drafts.
- AI action review, edit, reject, snooze, scheduled approval, background execution, safe retry rules, internal undo and audit events.
- Google OAuth with PKCE, encrypted refresh tokens, incremental Gmail/Calendar synchronization, email sends and Calendar mutations behind approval.
- OpenAI structured-output provider behind an explicit interface, tenant-bound context and source validation. No provider is called in demo mode.
- Document upload/download/search with local or Azure Blob storage, text/PDF extraction and configured-provider summaries.
- Stripe checkout/portal/invoices, verified idempotent subscription webhooks, trial state and metered AI usage.
- Durable jobs, retries, dead letters, event-driven workflow rules, notifications, analytics, exports and organization deletion.

The backend never treats the frontend or model output as an authorization boundary. The demo's conservative parser and editable follow-up templates are labelled development behavior, not a simulated live integration.

## Repository map

```text
backend/realty/       API routers, policies, models, providers and domain services
backend/migrations/  Versioned relational schema
backend/tests/       Service, API, security and provider-contract tests
frontend/            React/TypeScript application and shared design components
e2e/                 Playwright desktop/mobile acceptance journeys
scripts/             Reproducible frontend build
infra/               Azure Container Apps Bicep and deployment prerequisites
docs/                Architecture, operations, setup and acceptance evidence
.github/workflows/   Verification pipeline; no automatic production deployment
```

## Verify

```sh
python -m ruff check backend
python -m ruff format --check backend
python -m mypy backend/realty
python -m pytest
python -m alembic check
python -m pip_audit -r requirements.lock --disable-pip --no-deps
npm run lint
npm run typecheck
npm run format:check
npm run build
npm audit --audit-level=high
```

Start the API and worker on an isolated demo database, then `npx playwright install chromium` and `npm run test:e2e`. Tests create and modify fictional records; never aim them at customer data. For PostgreSQL integration tests, set `TEST_DATABASE_URL` to a **disposable** PostgreSQL database: tests create and drop their tables.

## Documentation

[Architecture](docs/architecture.md) Â· [Setup](docs/setup.md) Â· [Environment](docs/environment.md) Â· [Security](docs/security.md) Â· [AI design](docs/ai-architecture.md) Â· [Google](docs/google-integration.md) Â· [Billing](docs/billing.md) Â· [Database](docs/database.md) Â· [Deployment](docs/deployment.md) Â· [Testing](docs/testing.md) Â· [Troubleshooting](docs/troubleshooting.md) Â· [Acceptance](docs/acceptance.md)
