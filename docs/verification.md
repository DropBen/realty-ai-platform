# Verification evidence

Current application evidence: [CI run 34671651786](https://github.com/DropBen/realty-ai-platform/actions/runs/34671651786), commit `ce03214ebc588280b1dc82f01a26a6ed002f0d04`, September 12, 2026 UTC (September 11 America/New_York). All six jobs passed. Status and blockers: [project status](project-status.md). Earlier findings are retained as historical evidence in [completion-report.md](completion-report.md).

## Local Windows

`python -m pytest -p no:cacheprovider --junitxml=../../work/autonomy-final-tests.xml`: **168 passed, 2 PostgreSQL-only skips**, 64.06 seconds. Two upstream test-client deprecation warnings. Ruff formatting/lint, mypy, Bandit medium/high checks, Prettier/ESLint, TypeScript/web production build, npm audit and SQLite migration/drift checks passed. The migration regression converts prior-schema OAuth/action rows and verifies history retention and downgrade/re-upgrade. Local pip-audit was blocked by network restrictions; both Linux jobs passed it.

The running demo database was backed up to the private work directory before migration, then upgraded to `6bda8c204a71`. API and worker restarted; `/health/live`, `/health/ready`, `/api/v1/config` and the built page returned 200. No provider credentials or live messages were used.

## Linux CI

- PostgreSQL: **170 passed**, 104.20 seconds, including actual concurrent preference writing and worker lease renewal.
- SQLite: **168 passed, 2 intentional PostgreSQL-only skips**, 45.50 seconds.
- Desktop/mobile Chromium: **20 passed on the first attempt**, ten per device, 31.7/32.2 seconds. Includes account security, CRM/action review, failed demo delivery, listing import, axe and keyboard focus. Device environments are isolated and normal application rate limits remain enabled.
- Formatting, lint, type checking, Bandit, Python/JavaScript dependency audits, Alembic upgrade/drift, production build, Docker build and Bicep compilation passed.
- Offline AI safety corpus: **20/20**. These deterministic examples measure validation/authority behavior, not model accuracy.
- Both SQLite and PostgreSQL recovery/load drills passed. Refreshed JSON under `evidence/` is tied to the application commit by `authority-audit.json`.

PostgreSQL load: 198 requests, three users, 3,000 contacts, 300 properties; zero errors; p50 21.95 ms, p95 48.01 ms, maximum 112.05 ms. Approved tasks completed and cross-tenant requests were rejected. Tiny fictional PostgreSQL restore: 0.703 seconds, three files verified, restored sessions revoked and actions quarantined. These are short functional checks, not cloud RPO/RTO or capacity certification.

## Scope

Google/AI/Stripe HTTP is simulated in integration tests. The full realtor workflow uses real API/worker/database operations through source ingestion, reviewed preferences, approved email and timeline/audit persistence; only provider HTTP is replaced. No live Google, OpenAI, Stripe, SMTP, Blob or Azure acceptance occurred. Docker/browser checks ran in Linux CI because the local Windows daemon/IPC surfaces were unavailable. There are no failed required automated checks at this application head; external acceptance remains outstanding.
