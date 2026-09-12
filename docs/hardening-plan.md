# Autonomous completion plan

Baseline: branch feat/realtyai-foundation, commit 283091e. Existing architecture is preserved. Local 44-test suite, Ruff, mypy and production web build passed again before changes.

## Work sequence
1. Harden identity: verified email, reset/recovery, session revocation, password changes, TOTP/recovery codes, durable account mail, rate limits; backend/UI/security tests and migration.
2. Audit every route/domain boundary; address identity lookup transactions, authorization, quotas, worker heartbeat/fencing, input/upload and provider failure paths.
3. Complete core product gaps: commitments and reminders, document classification/entities with evidence, calendar all-day/timezone behavior, safe listing ingestion interfaces/fixtures.
4. Add deterministic AI evaluation corpus, expanded adversarial/failure/RBAC tests, desktop/mobile journeys and automated accessibility checks.
5. Add metrics/readiness/worker health, load baseline, backup/restore scripts and executed isolated recovery drill, CI/container/IaC validation.
6. Update environment/operations/security/setup docs, route inventory, precise verification matrix, readiness scores and external blockers. Commit changes, pass CI, prepare PR for merge and verify current branch protections before any merge.

## Boundaries
No live-provider success without credentials and evidence. No customer data in tests. Production deployment, DNS, commercial MLS access, independent security/manual accessibility and business acceptance remain external gates. Advanced telephony/OCR/route optimization are future scope per the completion directive.

## Evidence and progress
- Baseline local verification: 44 tests passed, two upstream deprecation warnings; Ruff and mypy passed; production build passed.
- Implementation and test results below are updated during work, not inferred from code presence.

- Identity commit ed073da: PostgreSQL and SQLite CI suites, migration drift, audits, Bandit, Docker and Bicep passed. Four new browser checks exposed an MFA form-state bug, a sign-out timing issue and an auth-page contrast failure; fixed in the next changes. Original 12 browser journeys passed.
- Route inventory test covers authentication on every API route. Added actual chunked-body bounds, rejection headers, Retry-After, atomic webhook/job deduplication, Stripe canonical-customer validation, bounded AI metering, same-transaction organization switching and renewable PostgreSQL job leases with stale-worker transaction fencing.
- Added source-preserving commitment review/reminders, document evidence/classification review, transactional file cleanup, timezone/DST/all-day calendar metadata, reviewed CSV/JSON listing ingestion, operator metrics, schema readiness, worker heartbeat and retention maintenance. New product tests passed locally; complete-suite and browser verification are ongoing.
