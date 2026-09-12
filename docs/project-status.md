# RealtyAI project status

Canonical status updated September 12, 2026. Application commit 8e6b6f6b20c34396361b9a708ff5a8724760d45f passed all six jobs in [CI run 34674184755](https://github.com/DropBen/realty-ai-platform/actions/runs/34674184755). Earlier completion reports are historical.

## Current milestone

Credential-free hardening of the realtor workflow is validated: observe a message, extract quoted evidence, recommend, review/edit/reject, approve, execute, record, audit and show the timeline. The API, worker and database are real; Google/OpenAI HTTP is simulated in the integrated acceptance test. Live-provider acceptance is the next meaningful gate.

## Overall implementation status

**Development ready; demo ready. Integration implementation available for live acceptance. Not production ready.** No staging deployment or external-account acceptance is claimed.

| Subsystem | Classification | Verified boundary |
|---|---|---|
| Authentication, recovery, MFA, sessions, CSRF, RBAC | IMPLEMENTED | API/security/browser cases; SMTP deliverability remains external |
| Tenant isolation | IMPLEMENTED | ORM scopes, write guards and composite keys; adversarial API tests; no database RLS |
| CRM, preferences, tasks, deals and timeline | IMPLEMENTED | Persistent CRUD, evidence and versioned review; stale preference writes and invalid undo rejected |
| Approval and execution | IMPLEMENTED | Withdraw/edit queued approvals, exact revision claim, current permissions, crash fencing, uncertain-send quarantine |
| Gmail/OAuth | PARTIALLY IMPLEMENTED / EXTERNAL DEPENDENCY | PKCE, encrypted refresh, scoped state, reconnect, cursor/checkpoint/dedupe and active sync reservation; no live acceptance |
| Calendar | IMPLEMENTED local / EXTERNAL DEPENDENCY Google | Local appointments, conflicts, timezone/recurrence imports; reviewed ETag conditional writes tested with simulated HTTP |
| AI extraction, answers and provenance | PARTIALLY IMPLEMENTED / EXTERNAL DEPENDENCY | Strict adapter/schema and quote/value checks, quotas, atomic source claim; real model quality/cost unmeasured |
| Demo intelligence | MOCKED / rule based | Explicit fictional data, conservative parser and editable templates; live providers blocked |
| Commitments/document review | IMPLEMENTED | Literal provenance, conditional review versions and recorded outcomes; isolated bounded PDF text extraction |
| Document storage | IMPLEMENTED local / EXTERNAL DEPENDENCY Azure | Upload/download/cleanup, storage-failure rollback and API responsiveness; Blob live behavior unverified |
| Listing ingestion | IMPLEMENTED CSV/JSON / MISSING live MLS | Preview/review/import and dedupe; no live MLS feed |
| Billing | PARTIALLY IMPLEMENTED / EXTERNAL DEPENDENCY | Durable checkout reconciliation and signed idempotent webhook contracts; no Stripe live/test-account acceptance |
| Jobs and observability | IMPLEMENTED | Leases, heartbeat/fencing, retry/dead states, safe operator retry, structured logs, metrics and health |
| Recovery and key rotation | IMPLEMENTED locally/CI | SQLite/PostgreSQL drills; global encrypted-field dry run/apply/rollback; cloud recovery remains unverified |
| Frontend and accessibility | IMPLEMENTED tested journeys | 26 browser cases, labelled email editor, cancellation/backoff/error recovery, axe and keyboard checks |
| Deployment infrastructure | PARTIALLY IMPLEMENTED / EXTERNAL DEPENDENCY | Docker build and Bicep compile; Azure runtime, DNS, alerts and sustained load not accepted |
| Advanced OCR, MLS, telephony and routing | MISSING / deferred | Explicitly outside this core milestone |

## Completed systems and latest changes

The [review/failure audit](review-failure-audit.md) records the implementation decisions. This continuation adds 28 backend cases, 12 frontend transport cases and six browser executions (three journeys on two devices), preserving the modular monolith and existing runtime dependencies.

- Queued actions can be withdrawn or edited until execution starts. Changed review versions cannot be claimed by stale workers or overwritten by stale reviewers.
- Actions, nested calendar payloads and timeline entries share the correct contact. Calendar approvals bind local state and provider ETag; changed/unversioned events require sync and fresh review.
- Overlapping extraction persists one set of facts, commitments and processing usage. Source changes and conflicting duplicate AI fields reject the result.
- Active manual/scheduled sync requests share a database reservation for the same resource. Operator retry conflicts return 409 and preserve the active job.
- Slow document storage leaves API liveness responsive. Browser transport handles cancellation, proxy HTML, malformed cookies/JSON, backoff and signed offsets without automatically retrying mutations.
- Email drafts use normal labelled fields and one dialog. The key-rotation command validates every encrypted field and rolls back all changes on corruption.

## Partially completed systems and known limitations

Provider HTTP simulations cannot establish actual consent, delivery, model accuracy or service behavior. One Google mailbox identity per user/workspace is supported; replacement identities remain unsupported. Overlapping analysis can consume two provider attempts even though only one result is persisted. External actions have no exactly-once guarantee; ambiguous outcomes stay quarantined.

Tenant isolation is enforced in the application and relational constraints. MFA is optional. PDF limits are not malware scanning. Audit records are append-only by API design, not cryptographically immutable. Key rotation requires quiescence and the current key. Listing feeds, OCR and advanced recurrence are deferred.

## Active engineering priorities

| Priority | Work | Status |
|---|---|---|
| P0 | Authority, tenant/demo isolation and current approval integrity | Demonstrated audit defects fixed and regression-tested |
| P1 | Core workflow persistence, failure handling, source integrity and provider contracts | Automated API/worker/database and adversarial cases pass |
| P1 | PostgreSQL, browser, security, build and migration verification | All six CI jobs pass at the application commit above |
| P1 | Google test integration and real AI evaluation | Next external gate; [minimal human actions](human-actions.md) |
| P2 | Cloud runtime/load/recovery and actual alerts/mail/billing acceptance | Requires staged services when that gate is reached |
| P3 | Broader capabilities | Defer until live core acceptance establishes a product need |

## External dependencies and human actions required

Only Google test integration and live AI access are requested for the next gate. [Human actions](human-actions.md) specifies what to provide, why, what it unlocks, independent blockers, exact configuration and the next engineering action for each.

An ignored .env.acceptance, independent encryption key, empty acceptance database, separate storage and local mail outbox are prepared. Acceptance uses http://127.0.0.1:8001; demo remains http://localhost:8000. Provider secrets are blank and AI remains disabled. These private files are excluded from Git, Docker context and the source archive.

Later commercial-release prerequisites are SMTP/sender-domain approval, Stripe test configuration, authorized Azure subscription/region/budget/domain, on-call/alert ownership, approved retention and recovery policies, and realtor/independent review. They do not block the local Google/AI exercise. Default main remains unchanged; an earlier automatic approval review required explicit merge authorization. PR #1 remains open.

## Tests

| Check | Result | Evidence/limit |
|---|---|---|
| Formatting/lint | PASSED | Ruff, Prettier, ESLint |
| Type checking | PASSED | mypy 32 application modules and TypeScript |
| Backend unit/API/integration/security | PASSED | PostgreSQL 198 passed (124.73s); SQLite 195 passed, three PostgreSQL-only skips (31.46s) |
| PostgreSQL concurrency | PASSED | Preference writers, renewable worker heartbeat and concurrent sync reservation |
| Frontend unit | PASSED | 12 transport/date cases; run on both browser CI jobs |
| E2E/accessibility | PASSED | 26/26, 13 desktop (43.1s) and 13 mobile (42.2s), first attempt |
| Security/dependency audits | PASSED | Bandit medium/high, pip-audit and npm audit; no known vulnerabilities reported |
| Migrations | PASSED | Upgrade/drift and prior-data downgrade/re-upgrade; SQLite date constraint and sync coalescing |
| Builds | PASSED | Production web assets, Docker image and Bicep |
| Operational drills | PASSED | SQLite/PostgreSQL recovery and mixed workload; 20/20 offline AI safety fixtures |
| Live provider/cloud/realtor acceptance | EXTERNAL DEPENDENCY | Not executed |

Local final suite: 195 passed, three PostgreSQL-only skips, 65.32 seconds. Two upstream test-client deprecation warnings remain. Browser/Docker execution is identified as Linux CI because local Windows IPC/daemon support was unavailable. Local pip-audit networking was unavailable; both Linux jobs passed it.

CI initially exposed an incorrect native-dialog selector and shared-user rate-limit exhaustion in the expanded browser fixtures. Both were corrected. Independent review accounts keep the real rate limit intact; no application safety checks or test assertions were relaxed.

## Deployment readiness

Migration head 9f24a781c6de is validated. Quiesce API/worker and back up before upgrading; old approved Calendar mutations return to review, and duplicate active read-sync jobs are coalesced. Sync existing Google events to obtain ETags before further changes. Downgrade retains the wider calendar identity column to avoid truncation.

The local demo backup passed SQLite integrity checking; eight contacts were retained after upgrade. API/worker restarted and live/ready/config/page returned 200. No existing encryption key was rotated.

PostgreSQL workload evidence: 198 requests, three users, 3,000 contacts, 300 properties, no errors, p50 26.69ms/p95 51.99ms; approved tasks completed and cross-tenant requests were rejected. Tiny fictional PostgreSQL recovery completed in 0.827s with three files verified, sessions revoked and actions quarantined. These are functional baselines, not capacity, cloud RPO/RTO or production SLO guarantees.

## Security status

The backend remains authoritative for permissions, changes, billing and external actions. AI/external content is untrusted; suggestions require schema/evidence validation and human review. Demo tenants remain isolated even if runtime configuration changes. No secret, live message or provider account was required for this audit. Automated controls are evidence, not security certification.

## Recommended next step

Run the isolated Google/AI acceptance described in human-actions.md. It will test the real service boundary the current simulations cannot prove. Further broad features would be speculative before those results. Fix any live discrepancy before pursuing cloud release or additional capabilities.
