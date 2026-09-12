# Verification evidence

Application commit 8e6b6f6b20c34396361b9a708ff5a8724760d45f passed all six jobs in [CI run 34674184755](https://github.com/DropBen/realty-ai-platform/actions/runs/34674184755), September 12, 2026 UTC. [Project status](project-status.md) is canonical; earlier completion reports are historical.

## Executed checks

- PostgreSQL: 198 passed, 124.73s, including independent preference writers, worker lease renewal and simultaneous sync reservations.
- SQLite CI: 195 passed, three intentional PostgreSQL-only skips, 31.46s.
- Windows local final suite: 195 passed, three skips, 65.32s.
- Frontend unit: 12 passed. Desktop/mobile E2E: 26 passed on the first attempt, 13 per device, 43.1s/42.2s. Includes account security, approval withdrawal, labelled draft editing with axe, proxy-error recovery, CRM, listing imports and keyboard focus.
- Ruff/Prettier/ESLint, mypy (32 modules), TypeScript, Bandit medium/high, pip-audit/npm audit, migration upgrade/drift and regression, web/Docker builds and Bicep compile all passed.
- Offline AI corpus: 20/20. Real model accuracy remains unmeasured.
- SQLite/PostgreSQL load and recovery drills passed. The JSON reports in evidence/ are from this run; authority-audit.json binds them to the application revision.

Two upstream test-client deprecations and GitHub action-runtime deprecation notices remain. No required automated check is failing at this application revision.

## Failed checks that were corrected

The initial review regressions reproduced eight failures before implementation. The first browser run found an invalid explicit-role selector for a native dialog and a toast fixture assumption. The next run exceeded the unchanged user rate limit because all expanded journeys shared one demo identity. The final run uses a separate review-fixture account and passes all browser cases without retries; security limits remain enabled.

## Operations and local runtime

PostgreSQL functional workload: 198 requests, three users, 3,000 contacts, 300 properties, zero errors, p50 26.69ms/p95 51.99ms/max 145.82ms. Approved tasks and cross-tenant rejection passed. Tiny PostgreSQL recovery: 0.827s, three verified files, sessions revoked and actions quarantined. These are not production capacity or recovery guarantees.

The local demo was quiesced and backed up; SQLite integrity check passed. Upgrade to 9f24a781c6de retained eight contacts. Restarted API/worker returned 200 for /health/live, /health/ready, /api/v1/config and the production-built page. A separate empty local acceptance database and ignored private environment profile were prepared; no credentials were supplied or existing key rotated.

## Scope limits

Provider integration tests replace only HTTP while executing real API/worker/database operations through ingestion, evidence, review, approval, delivery records and audit/timeline. Simulations do not prove live Google/OpenAI/Stripe/SMTP/Blob or Azure behavior. Browser/container checks ran on Linux because local Windows IPC/daemon support was unavailable. The next required validation is the [isolated live workflow](human-actions.md).
