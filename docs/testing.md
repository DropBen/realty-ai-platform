# Testing and reproducible evidence

Tests use fictional data. Backend fixtures create and drop their tables; `TEST_DATABASE_URL` must be disposable. Never aim browser, load or recovery drills at customer data. Tests use `respx` provider contracts, not live accounts.

## Backend and build

From the activated repository environment (`PYTHONPATH=backend` or editable package installed):

```sh
python -m ruff check backend scripts
python -m ruff format --check backend scripts
python -m mypy backend/realty
python -m bandit -r backend/realty -ll -q
python -m pytest -p no:cacheprovider --cov=realty --cov-report=xml
python -m alembic upgrade head
python -m alembic check
python -m pip_audit -r requirements.lock --disable-pip --no-deps
npm run lint
npm run typecheck
npm run format:check
npm run build
npm audit --audit-level=high
```

Coverage includes authentication policy on every API route; identity verification/reset/MFA/replay/session IDOR; CSRF and actual chunked body bounds; tenant lookups/relationships/role checks; action review/version/tampering/expiry/reauthorization/undo; duplicate jobs/webhooks and stale leases; provider failure/evidence/metering; commitments/reminders; DST/all-day/recurrence imports; listing conflicts/isolation; document rollback/delete/evidence and actual isolated PDF parsing; metrics and exact-schema readiness. The PostgreSQL-specific test verifies heartbeat renewal during a long dispatch. SQLite deliberately skips that multi-connection test.

## Browser and accessibility

Run a freshly migrated/seeded demo API and worker with `MAIL_BACKEND=outbox`, a generated encryption key and `APP_ORIGIN=http://localhost:8000`. Then:

```sh
npx playwright install --with-deps chromium
npm run test:e2e
```

The 18 configured tests cover desktop/mobile routes and width; contact/preferences/timeline; structured command; action approval→worker→timeline; explicit unconfigured Google; isolated signup; CSV preview/import/persistence; TOTP/recovery/session workflows; and axe WCAG A/AA/2.1 checks plus dialog initial/Escape/return focus. They use real HTTP/API state, not a mock UI. CI gives desktop and mobile their own freshly seeded database/API/worker; each Playwright project uses a single worker and normal rate limits. Repeated full runs against the same process can hit legitimate per-user/login limits; use a fresh isolated environment or wait for Retry-After. Do not weaken production limits to pass tests.

Automated checks cover dashboard, contacts, security settings and a contact dialog. Screen-reader, Safari/Firefox, assistive-device, broader-content and real-user testing remain separate acceptance. This Windows host cannot initialize browser IPC; actual Chromium execution and screenshot evidence come from Linux CI.

## Offline AI evaluations

```sh
python scripts/evaluate.py --output work/ai-evaluations.json
```

The versioned 20-case `evals/cases.json` corpus exercises unknown/negated/invalid facts, exact numeric evidence, hostile instructions, excluded protected attributes, forbidden action payloads and schema constraints. It measures deterministic validation rules, **not live model accuracy**. Live evaluation must add approved representative staging examples, expected facts/citations, adversarial prompts and human scoring before enabling model-backed production features.

## Load baseline and recovery

```sh
python scripts/load_baseline.py --work-dir work --output work/load-sqlite.json
python scripts/load_baseline.py --postgres --work-dir work --output work/load-postgres.json
python scripts/recovery_drill.py --work-dir work --output work/recovery-sqlite.json
python scripts/recovery_drill.py --postgres --work-dir work --output work/recovery-postgres.json
```

PostgreSQL requires separately created empty `realty_load_*` and `realty_drill_*` databases configured through `LOAD_DATABASE_URL`, `DRILL_DATABASE_URL` and `RESTORE_DATABASE_URL`. CI provisions them. Scripts start/stop their own API/worker processes and generate unique scratch directories. Load baseline uses three users, 3,000 contacts, 300 properties and 198 measured mixed requests, including approval and worker completion. It verifies results and tenant denial; it is too short/small to claim an SLO, saturation point or capacity. Recovery verifies real dump/restore plus documents and safe quarantine. See [backup and restore](backup-restore.md).

[verification.md](verification.md) records actual results and commit/workflow links. CI also builds Docker and compiles Bicep. Neither operation proves an Azure deployment or real provider integration.

## Authority-audit regressions

`test_authority_regressions.py` covers invalid inputs/configuration, OAuth workspace and revocation boundaries, newer manual edits, invalid undo, terminal approval handling and a PostgreSQL concurrent writer. `test_authority_migration.py` tests real prior-schema conversion. `test_provider_safety.py` covers permanent demo isolation, reconnect failures, stale credential failure races and secret-safe config errors. `test_billing_reconciliation.py` covers pending checkout retries, canonical cancellation/replacement and old events. `test_realtor_workflow.py` uses real API/worker/database code through the full email/evidence/approval/delivery loop, with Google and AI HTTP fixtures. The added browser journey proves failed demo email remains unsent and can return for review.

The browser suite now contains 20 configured cases (10 desktop, 10 mobile). Exact current results are maintained in [project status](project-status.md); fixtures do not establish real provider acceptance.
