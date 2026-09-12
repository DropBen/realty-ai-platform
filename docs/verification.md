# Verification evidence

Evidence is tied to executed commits/workflows, not inferred from code presence. Tests use fictional data; provider contracts use controlled HTTP responses.

## Local Windows execution

- `python -m pytest -p no:cacheprovider --junitxml=../../work/final-tests.xml`: **110 passed, 1 PostgreSQL-only skip**, 75.79 seconds. Two upstream test-client deprecation warnings.
- Focused identity/PDF/evaluation: **34 passed**. After calendar serialization: integration/document suite **16 passed**.
- Ruff lint and format: passed (50 Python files). Mypy: passed (31 application modules). Bandit medium/high checks: passed.
- ESLint, Prettier, TypeScript and production web build: passed. SQLite Alembic head and model drift: passed.
- Offline AI evaluation: **20/20**; deterministic source/schema/authority checks, not live model accuracy.
- Local recovery: verified files, row counts, schema, tenant separation, session invalidation, action quarantine and corruption/overwrite rejection. Local mixed load: 198 requests, three users, 3,000 contacts and 300 properties, zero errors. Exact JSON reports in `evidence/`.
- Refreshed application: health/ready 200, demo login 200, briefing 200, worker available true.
- Four starter alert rules parsed as YAML. They have not been installed in or validated by a live monitoring service.

## Completed Linux CI

[Run 34668978988](https://github.com/DropBen/realty-ai-platform/actions/runs/34668978988) verified final implementation/test-environment commit `fe07875269c4315dddf0f02302ca74d532ae5154`. All six jobs passed:

- **111 PostgreSQL tests passed**, including actual concurrent lease heartbeat.
- **110 SQLite tests passed, one intended PostgreSQL-only skip**.
- **All 18 browser tests passed on the first attempt**: nine desktop and nine mobile. These include MFA/recovery/session workflows, axe/keyboard dialog checks, listing import and original CRM/action journeys. Each device has its own fresh database/API/worker. This resolved the legitimate shared-account rate-limit interference disclosed in historical run 34668757058; no production limits were weakened.
- Python/frontend formatting, lint, types, Bandit, migration/drift, dependency audits, web build, Docker image and Bicep compilation passed. npm found zero vulnerabilities; Python reported no known vulnerabilities.
- SQLite and PostgreSQL recovery/load drills and 20-case evaluation passed in their own CI job.


Specific PostgreSQL operational reports checked into `evidence/` originate from [run 34668452691](https://github.com/DropBen/realty-ai-platform/actions/runs/34668452691), application commit `c552fac4fbf7f0b2deca60e993b030fbd8ef8e18`: restore 0.736 seconds for tiny fictional data; load 198 requests, zero errors, p50 26.55 ms, p95 49.66 ms, max 106.51 ms, approved tasks completed and cross-tenant request rejected. The complete job passed, although unrelated browser/type checks in that historical run failed and were subsequently fixed.

These are short functional baselines, not production capacity, SLO, Azure recovery or live-provider certification. Screenshot review confirmed desktop/mobile dashboard layout. Browser and Docker execution were not possible on this Windows host (IPC/daemon unavailable); Linux CI supplies that evidence. Azure provisioning, real Google/AI/Stripe/SMTP/Blob acceptance, screen-reader assessment and independent penetration testing were not executed.

See [testing](testing.md) for commands and [completion report](completion-report.md) for the 25-area matrix, scores, blockers and launch gates. The subsequent documentation-only update records these completed results and the merge approval boundary. PR #1 is ready for review, but automatic approval review blocked merging without explicit user approval. `main` remains the initial README. Its current workflow/state is available on [PR #1](https://github.com/DropBen/realty-ai-platform/pull/1).
