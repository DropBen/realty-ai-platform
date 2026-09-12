# RealtyAI

Current status, engineering priorities, verified limits and exact human prerequisites: **[Project status](docs/project-status.md)**. Earlier completion reports describe previous snapshots.

**The AI handles the busywork. The realtor handles the relationship.**

RealtyAI is a modular real-estate CRM with a working API, relational database, background worker, React workspace and approval-driven intelligence. It runs locally without production credentials in an explicitly labelled demo workspace.

This is an implemented and tested application, **not a certified production release**. Identity recovery/MFA, PostgreSQL tests, automated accessibility, offline AI evaluations, and isolated load/recovery drills are included. Live provider acceptance and Azure deployment remain separate launch gates. See the [completion report](docs/completion-report.md) and [verification evidence](docs/verification.md).

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

- Password authentication, email verification/recovery, optional TOTP and recovery codes, session management, CSRF, five roles and organization switching.
- Contacts/leads/buyers/sellers, confirmed preferences, source facts, a relationship timeline, notes/calls/showing feedback, properties, deals and transaction milestones.
- Tasks, local appointments, calendar conflict detection, available-time suggestions and meeting preparation.
- Data-derived briefing, bounded natural-language search, explainable buyer/property matching, email extraction, proposed commitments and follow-up drafts.
- AI action review, edit, reject, snooze, scheduled approval/withdrawal, background execution, safe retry rules, internal undo and audit events. Email drafts use labelled form fields.
- Google OAuth with PKCE, encrypted refresh tokens, incremental Gmail/Calendar synchronization, email sends and Calendar mutations behind approval.
- OpenAI structured-output provider behind an explicit interface, tenant-bound context and source validation. No provider is called in demo mode.
- Reviewed CSV/JSON listing import, source-preserving commitment review/reminders, and document classification/entity proposals.
- Authorized document storage/downloads, isolated PDF text parsing, evidence validation and explicit classification review.
- Stripe checkout/portal/invoices, verified idempotent subscription webhooks, trial state and metered AI usage.
- Renewable/fenced worker leases, retries/dead letters, event-driven workflows, notifications, metrics, analytics, exports and durable document deletion.
- Backup/restore tooling, isolated PostgreSQL/SQLite recovery and load drills, deterministic AI evaluations and operator runbooks.

The backend never treats the frontend or model output as an authorization boundary. The demo's conservative parser and editable follow-up templates are labelled development behavior, not a simulated live integration.

## Repository map

```text
backend/realty/       API routers, policies, models, providers and domain services
backend/migrations/  Versioned relational schema
backend/tests/       Service, API, security and provider-contract tests
frontend/            React/TypeScript application and shared design components
e2e/                 Playwright desktop/mobile acceptance journeys
scripts/             Frontend build, AI evaluation, load baseline and recovery tooling
evals/               Versioned adversarial and evidence fixtures
infra/               Azure Container Apps Bicep and deployment prerequisites
docs/                Architecture, operations, setup and acceptance evidence
.github/workflows/   Verification pipeline; no automatic production deployment
```

## Verify

```sh
python -m ruff check backend scripts
python -m ruff format --check backend scripts
python -m mypy backend/realty
python -m bandit -r backend/realty -ll -q
python -m pytest -p no:cacheprovider
python scripts/evaluate.py --output work/ai-evaluations.json
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

[Architecture](docs/architecture.md) · [Setup](docs/setup.md) · [Environment](docs/environment.md) · [Security](docs/security.md) · [AI design](docs/ai-architecture.md) · [Google](docs/google-integration.md) · [Billing](docs/billing.md) · [Database](docs/database.md) · [Deployment](docs/deployment.md) · [Testing](docs/testing.md) · [Troubleshooting](docs/troubleshooting.md) · [Acceptance](docs/acceptance.md)

[Account security](docs/account-security.md) · [Operations](docs/operations.md) · [Backup and restore](docs/backup-restore.md) · [Listing imports](docs/listing-imports.md) · [API inventory](docs/api-routes.md) · [Completion report](docs/completion-report.md)
