# RealtyAI project status

Canonical engineering status. Updated September 11, 2026 (verification timestamps may be September 12 UTC). Earlier completion reports are historical snapshots, not release certification.

## Current milestone

Harden the approval-driven realtor workflow for external integration acceptance. Preserve the FastAPI/SQLAlchemy modular monolith and React application. Fix demonstrated authority, data integrity and failure-reporting defects before adding capabilities.

## Overall implementation status

The application works locally and in automated CI. Development and demo use are supported. Provider adapters have simulated HTTP coverage; live Google, OpenAI, Stripe, SMTP and Azure behavior is unverified. This is **not production ready**.

Classification refers to the verified behavior in each row, not the feature name. `EXTERNAL DEPENDENCY` never implies live acceptance has passed.

| Subsystem | Classification | Code evidence and practical boundary |
|---|---|---|
| Authentication, sessions, CSRF, RBAC | IMPLEMENTED | `security.py`, `identity.py`, identity/security API and browser tests. Verified-email gate and optional TOTP/recovery exist; SMTP delivery needs acceptance. |
| Tenant isolation | IMPLEMENTED | ORM scoping, write guards, composite relational keys and adversarial tests. Explicit identity/worker discovery queries span organizations; no database RLS. |
| CRM, preferences, timeline, tasks, deals | IMPLEMENTED | Persistent APIs, evidence records and UI workflows. New audit adds approval preconditions and validated undo. |
| Action review and execution | IMPLEMENTED | Versioned review, payload digest, current permissions, durable jobs and uncertain-send quarantine. New audit closes stuck approvals and stale preference overwrites; failed/uncertain actions have dedicated review filters. |
| Google OAuth and synchronization | PARTIALLY IMPLEMENTED / EXTERNAL DEPENDENCY | PKCE, refresh, full/incremental import, cursor recovery and encrypted credentials exist. Workspace/callback permission checks and durable reconnect-required failures are tested. One mailbox identity per user/workspace; replacement-account import is unsupported. No live consent/sync/send acceptance. |
| Calendar | IMPLEMENTED local / EXTERNAL DEPENDENCY Google | Local appointments/conflicts, all-day/DST/recurrence-instance imports and approved provider mutations. No full recurrence-series editor or route optimization. |
| AI extraction, answers and provenance | PARTIALLY IMPLEMENTED / EXTERNAL DEPENDENCY | Actual strict-schema adapter, source/quote/value checks, quotas and proposed facts. Deterministic demo rules are MOCKED model behavior; offline fixtures do not measure live model quality. |
| Realtor email-to-action workflow | IMPLEMENTED with simulated providers | Actual API, worker and database path: ingest → evidence → review → preference update → draft → approve → send → record/audit. HTTP fixtures replace Google/AI; live delivery remains unverified. |
| Documents | IMPLEMENTED local / EXTERNAL DEPENDENCY Azure | Bounded upload, isolated PDF extraction, provenance/review, download and durable deletion. No antivirus or OCR engine. Scanned PDFs explicitly require OCR. |
| Listings and matching | IMPLEMENTED import / MISSING live MLS | CSV/JSON preview, validated import/deduplication/manual-edit protection and explained matching. Live feed depends on a licensed provider contract; an adapter interface is not a working feed. |
| Billing | PARTIALLY IMPLEMENTED / EXTERNAL DEPENDENCY | Signed webhook handling, canonical subscription transitions, durable checkout retry/session reuse and portal adapters. Real test-mode lifecycle and commercial policy remain unvalidated. |
| Durable jobs and operational controls | IMPLEMENTED | Claims, deduplication, retries, PostgreSQL heartbeat/fencing, cleanup, status/metrics and recovery tests. SQLite is a local single-worker environment. |
| Backups and restore | IMPLEMENTED isolated drills | SQLite/PG snapshots, file checksums, empty-target restore, session revocation/action quarantine. Managed-cloud restore and production RPO/RTO are unverified. |
| Frontend and accessibility | IMPLEMENTED core / PARTIALLY IMPLEMENTED accessibility | Responsive real-API workflows, browser/axe/keyboard tests. Real-agent and assistive-technology acceptance remain outstanding. |
| Deployment and monitoring | PARTIALLY IMPLEMENTED / EXTERNAL DEPENDENCY | Docker/Bicep/CI, health, metrics and alert rules exist. Azure resources, DNS, alert delivery and on-call ownership are not established. |
| Telephony, transcription, advanced OCR | MISSING | No live provider and no complete operational workflow. UI must not imply otherwise. |

## Completed systems and audit findings

The implementation above retains working CRM, identity, evidence review, queue, recovery and demo foundations. During this audit, new regression cases reproduced invalid-date 500s, fail-open configuration, OAuth workspace/permission gaps, stale CRM writes, invalid undo and stuck approvals. The local backend suite now passes with these fixes; final Linux/browser/operational verification is pending.

## Partially completed systems and known limitations

Provider acceptance, cloud runtime, sustained production-shaped load and independent security/accessibility/user acceptance remain incomplete. A single Google mailbox identity is intentionally retained across disconnect/reconnect to prevent imported identity collisions. Advanced capabilities are outside this milestone. Tenant isolation is application-enforced; MFA remains optional. Document parsing limits do not constitute malware scanning. AI suggestions are untrusted and never grant application authority.

## Active engineering priorities

| Priority | Work | Status |
|---|---|---|
| P0 | Bind OAuth state to workspace and recheck current permission after network exchange | Fixed; local regressions pass, CI pending |
| P0 | Reject unsafe configuration and preserve stored demo isolation across runtime changes | Fixed; local checks pass, CI pending |
| P1 | Preserve newer preferences, validate undo and terminate invalid approvals visibly | Fixed; local workflow passes, PostgreSQL concurrency pending CI |
| P1 | Reject malformed provider responses; require actual resource confirmation before recording delivery | Fixed; local adversarial tests pass, CI pending |
| P1 | Validate provider failures/reconnect and billing identity transitions | Fixed; reconnect and billing reconciliation contract tests pass |
| P1 | Run complete automated suite, migration checks and CI/browser/operational gates | Local checks pass; Linux CI pending |
| P1 | Live staged workflow acceptance with provider accounts | External dependency; exact steps below |
| P2 | Sustained cloud load/recovery, alert delivery, independent assessment | Depends on staging and reviewers |
| P3 | Multiple mailbox identities, live MLS, advanced recurrence/OCR/telephony | Defer until core integration acceptance establishes the next product need |

## External dependencies and human actions required

Enter secrets through the deployment secret mechanism, never chat or Git. Nonsecret settings use runtime environment variables; Key Vault values are mapped through `secretReferences`/`secretEnvironment` in `infra/apps.bicep`. Engineers can complete adapter tests and fixes without these credentials.

| Item | Why required | What to provide | Where to configure | Blocking? |
|---|---|---|---|---|
| Google Cloud OAuth web application | Verify actual consent, scopes, sync and approved delivery | Cloud project, enabled Gmail/Calendar APIs, OAuth Web Application client, consent test users, authorized test mailbox/calendar | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, exact `GOOGLE_REDIRECT_URI` ending `/api/v1/integrations/google/callback`; secret in Key Vault, connect through Settings | Live Google acceptance only |
| OpenAI project and evaluation allowance | Measure real structured extraction quality, cost and latency | Project API key, model access and representative approved test data/spend ceiling | `AI_PROVIDER=openai`, `AI_MODEL`, `AI_API_KEY`, `AI_TIMEOUT_SECONDS`, `AI_MONTHLY_LIMIT` | Live AI evaluation only |
| Stripe test account setup | Validate checkout, cancellation, portal and signed billing events | Test API key, recurring price, portal configuration and webhook signing secret | `STRIPE_SECRET_KEY`, `STRIPE_PRICE_ID`, `STRIPE_WEBHOOK_SECRET`; endpoint `/api/v1/webhooks/stripe` | Live test billing only; live charges require business approval |
| SMTP and sender domain | Validate account verification/recovery delivery | SMTP service credentials and approved sender; DNS ownership for SPF/DKIM/DMARC | `MAIL_BACKEND=smtp`, `MAIL_FROM`, `SMTP_HOST/PORT/USERNAME/PASSWORD`, `SMTP_STARTTLS=true` | Real signup/recovery acceptance |
| Azure deployment access and budget | Run the actual staged runtime | Authorized subscription/resource group, deployment role, approved region/budget and domain/DNS control | Protected Bicep parameters; Container Apps, PostgreSQL, Blob, ACR, Key Vault and DNS | Cloud staging/load/recovery only |
| Operational and release ownership | Approve real policies and acceptance | Alert recipient/on-call owner, retention/legal-hold policy, support recovery policy, RPO/RTO and reviewer access | Private operational/release record and provider alert/backup settings | Commercial launch |
| Realtor and independent reviewers | Validate real usefulness, accessibility and security | Test users/reviewers and permission to use representative staging data | Staging app and private findings tracker | Release acceptance |
| Explicit PR merge approval | Earlier automatic approval review rejected updating default `main` without explicit merge authorization | Approve merging the verified PR #1 when ready | This task; recheck current CI/head before merge | Merge only, not engineering on the feature branch |

## Tests

Baseline before this audit: CI at `9537b2e4af6fea561d817114c4cd83b41ada5bf3` passed six jobs. Current local run: **168 passed, 2 skipped**, 64.06 seconds. The two intentional skips require PostgreSQL (heartbeat and concurrent preference writer). Ruff formatting/lint, mypy, Bandit, ESLint/Prettier, TypeScript/production build, npm audit and isolated migration upgrade/downgrade/drift checks passed. Two upstream test-client deprecation warnings remain. Linux CI will validate both PostgreSQL cases, all 20 browser cases, dependency audits, Docker/Bicep and recovery/load/evaluation drills; those results are pending for this change set.

## Deployment readiness

**Development ready; demo ready. Integration implementation available, live integration acceptance pending.** Staging configuration and validation are the next external milestone. No production deployment or merge is claimed. Migration `6bda8c204a71` invalidates outstanding OAuth requests and returns historical approved CRM updates to review; deploy with API/worker quiesced and re-review affected suggestions. It retains application records and does not send external requests.

## Security status

Incremental controls are tested, not a security certification. No LLM can authorize writes, billing or external actions. Provider content is data; evidence and typed payload checks remain server-side. Demo mode blocks live AI/mail/Google/billing paths. Secrets remain ignored/protected. New audit results supersede broad completion claims in earlier snapshots.

## Recommended next steps

Finish this hardening verification, then run the staged Google email-to-review-to-delivery workflow and live AI evaluation on approved test data. Fix observed integration discrepancies before expanding feature scope. Cloud deployment and billing acceptance follow once their independent credentials and budgets are available.
