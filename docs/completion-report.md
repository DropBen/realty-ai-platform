# RealtyAI completion and independent-audit handoff

Evidence date: September 11, 2026 America/New_York (CI timestamps September 12 UTC). This report describes the existing application after incremental completion/hardening. The FastAPI/SQLAlchemy/React architecture was preserved.

## Executive summary

RealtyAI is a functional CRM and approval-driven assistant with local demo operation, durable background execution and explicit provider boundaries. Authentication recovery/MFA, evidence review, listing ingestion, calendar edge cases, worker reliability, metrics, recovery tooling and tests have been added. It is ready for an independent code audit and staged acceptance after the final verification below. **It is not declared production-ready:** live providers, Azure runtime, real alert delivery, cloud recovery and human acceptance remain unverified.

Repository: [DropBen/realty-ai-platform](https://github.com/DropBen/realty-ai-platform). Implementation: [PR #1](https://github.com/DropBen/realty-ai-platform/pull/1).

Pre-merge audit: `main` was the initial README commit `5b11c25`; PR #1 contained the application, was mergeable, had no reviews/unresolved threads, and `main` had no protection or rulesets. The reviewed application commit is `be1a8b8d91c0f997e32d7cb15bc5b39ef01936a2`. Merge is gated on successful final CI; the PR page records the definitive merge result. No production deployment is triggered.

## What changed

1. **Identity:** single-use expiring email verification/reset tokens; encrypted durable account mail and SMTP/outbox transports; production verified-email gate; password change; device/session listing and revocation; optional TOTP with replay prevention, enrollment expiry and ten hashed recovery codes; factor-preserving recovery and organization deletion; generic recovery messages and persisted failed-attempt rate limits. Added complete account UI and browser journeys.
2. **Authorization and security:** explicit authentication-policy inventory for all 75 API routes; repaired cross-organization identity lookup transaction handling; bounded actual streamed request bytes before mutations; security headers on early errors; Retry-After; atomic webhook/job insertion; canonical Stripe customer validation; bounded provider usage fields; serialized quota reservations and calendar conflict checks.
3. **AI and source integrity:** values must match their literal supporting quote, including normalized numbers; protected/unsupported fields and action payloads are rejected. Commitments retain source text and require an owner/deadline review before reminders. Document classifications/entities remain source-linked proposals with explicit hash-bound review. Added a 20-case offline adversarial/evidence corpus and executable evaluation report. There is no claim of measured live model accuracy.
4. **Product workflows:** commitment confirmation/dismissal/completion and stale-review protection; versioned due reminders; all-day/timezone/DST and recurrence-instance import metadata; quoted CSV/JSON listing preview/import with revision deduplication, tenant scope and protection of manual edits. Added usable UI for each core review flow.
5. **Documents:** upload rollback cleanup, persistent post-commit blob deletion including organization removal; extraction in an isolated Python process, 30-second timeout and Linux 20-second CPU/512-MB address-space limits; encrypted/active/malformed/over-page-limit failures and explicit OCR-required status. This is bounded parsing, not antivirus or a full OS sandbox.
6. **Workers and operations:** renewable PostgreSQL leases, monotonic attempt fencing at flush/commit, safe operator retries, bounded import checkpoints, worker heartbeat, exact-schema readiness, protected metrics, maintenance cleanup, starter alerts and runbooks. Uncertain external actions never silently resend.
7. **Recovery and testing:** PostgreSQL/SQLite database+document snapshots and verified restore into empty targets; revoke restored sessions/tokens and quarantine approved/executing actions; executed fictional recovery and mixed-load drills; CI PostgreSQL services, backend/security/provider tests, desktop/mobile browser and axe/keyboard tests, audits, Docker and Bicep validation. Updated the environment matrix, architecture/security/AI/deployment docs and API inventory.

## Tests actually executed

[Application CI run 34668757058](https://github.com/DropBen/realty-ai-platform/actions/runs/34668757058) passed all five jobs: **111 PostgreSQL tests; 110 SQLite tests and one intended skip; 17 browser tests passed initially and one passed on retry**; operational drills, lint/types/Bandit, dependency audits, migrations, production web build, Docker and Bicep passed. Inspection traced the browser retry to legitimate rate limiting on the shared demo account. The final workflow separates desktop/mobile environments to remove that test interference without weakening limits; its completed result is recorded on PR #1 and in the final handoff.

Local Windows: `python -m pytest -p no:cacheprovider --junitxml=../../work/final-tests.xml` → **110 passed, 1 skipped**, 75.79 seconds, two upstream test-client deprecation warnings. The skip is the PostgreSQL-only concurrent heartbeat test. Focused identity/PDF/evaluation run → **34 passed**; post-calendar-change integration/document run → **16 passed**. Ruff lint/format, mypy, Bandit medium/high scan, ESLint/Prettier, TypeScript production build and SQLite migration drift checks passed. Browser IPC and Docker daemon were unavailable locally; Linux execution is identified separately rather than claimed as local.

`python scripts/evaluate.py --output docs/evidence/ai-evaluations.json` → **20/20** deterministic cases. The fixtures check schema/evidence and authority boundaries, not model-generated factual quality.

Executed operational evidence for application `c552fac4fbf7f0b2deca60e993b030fbd8ef8e18` in [CI run 34668452691](https://github.com/DropBen/realty-ai-platform/actions/runs/34668452691): PostgreSQL restore verified in **0.736 seconds** for a tiny fictional two-tenant snapshot; three files checked, one session revoked, two actions quarantined; tenant isolation, existing-target rejection and corrupted-checksum rejection passed. PostgreSQL mixed workload: **198 requests, 3 users, 3,000 contacts, 300 properties; zero errors; p50 26.55 ms, p95 49.66 ms, max 106.51 ms**, plus successful approved-task execution and cross-tenant rejection. SQLite recovery/load also passed. These are short runner/local baselines, not capacity, cloud RPO/RTO or sustained-load guarantees. JSON evidence is under `docs/evidence/`.

Exact reproducible commands and constraints are in [testing](testing.md), [verification](verification.md) and [backup/restore](backup-restore.md). Provider contract tests do not establish real account permissions, consent, delivery or payment behavior.

## Production-readiness assessment

Subjective engineering assessment out of 100, **not measured compliance or a probability of safe launch**. No aggregate score overrides a release gate.

| Area | Score | Basis and remaining gate |
|---|---:|---|
| Engineering | 86 | Working modular application, relational migrations, guarded transactions and reproducible build; independent review and staged runtime needed |
| Security | 78 | Recovery/MFA, tenancy/RBAC/CSRF/evidence/file controls tested; opt-in MFA, no RLS, no independent penetration test or live threat review |
| AI | 72 | Explicit authority boundary, exact evidence and offline regressions; live precision/hallucination/red-team measurement absent |
| Integrations | 58 | Executable Google/AI/Stripe/SMTP/Blob adapters and contracts; no live account acceptance, licensed MLS still an adapter boundary |
| Infrastructure | 58 | Docker/Bicep validate; actual Azure networking, identity, DNS and runtime not deployed |
| UX | 83 | Working responsive flows, visible errors/unknowns, browser and automated accessibility coverage; real-agent UAT and assistive-tech review needed |
| Testing | 85 | Broad backend/PG/SQLite/browser/adversarial/recovery coverage; limited browser set, short load baseline and no live-provider certification |
| Operations | 67 | Health/metrics/leases/restore/runbooks implemented; real alerts, retention ownership, cloud drills and on-call process not established |

## Required 25-area verification matrix

“Implemented + verified” means the specified automated/local behavior was observed; it does not imply live production certification. “Implemented + not live verified” identifies functioning adapter code with external acceptance pending. Future items are explicitly scoped below.

| # | Area | Status | Evidence / practical limit |
|---|---|---|---|
| 1 | Repository | Implemented + verified; merge gated by final CI | Audited base/head, branch rules and reviews; final PR/commit state above |
| 2 | Backend | Implemented + verified | API/service tests, type/lint/build; 75 explicit API authentication policies |
| 3 | Frontend | Implemented + verified | Typed React build and actual desktop/mobile workflows; no production traffic |
| 4 | Database | Implemented + verified | Concrete Alembic head `2375a43c78e9`, SQLite/PG checks and recovery; managed Azure instance pending |
| 5 | Authentication | Implemented + verified | Verification/reset/MFA/recovery replay/session tests and UI; SMTP delivery pending |
| 6 | RBAC | Implemented + verified | Five central roles, worker reauthorization, elevated review/billing/member/delete permissions; future endpoints require review |
| 7 | Tenancy | Implemented + verified | Scoped reads/writes/IDs/relationships, export/import/documents, recovered tenant isolation; privileged SQL has no RLS |
| 8 | AI | Implemented + verified boundary; live quality blocked | Schema, source IDs, exact quotes/numbers, approval snapshots and 20 offline cases; model evaluation pending |
| 9 | Gmail | Implemented + not live verified | OAuth/PKCE/refresh/cursors/dedupe/error contracts; consent and mailbox/send acceptance need Google account |
| 10 | Calendar | Implemented + not live verified | DST/all-day/recurrence metadata and conflicts tested; real provider mutations/series editing not certified |
| 11 | Documents | Implemented + verified local path | Upload/download isolation, extraction limits/evidence/review/rollback/deletion; Azure and scanning acceptance pending |
| 12 | Properties | Implemented + verified | CRUD, explainable preference matching, reviewed import; no valuation model |
| 13 | MLS | Partial; live adapter blocked externally | CSV/JSON import works; licensed provider selection/contract/credentials required for a live feed |
| 14 | Scheduling | Implemented + verified core | Local office hours, conflicts and preparation; travel/route optimization and advanced recurrence future |
| 15 | Billing | Implemented + not live verified | Signature, duplicate/out-of-order/canonical customer and entitlements tested; test-mode customer lifecycle pending |
| 16 | Notifications | Implemented + verified | In-app notices, commitment due reminders and job state; live account-mail delivery pending, no SMS |
| 17 | Workers | Implemented + verified | Claim/dedupe/retry/fence/heartbeat contracts; short load completion; production scaling pending |
| 18 | Security | Implemented controls + verified automated checks | CSRF/origin/body/rate/identity/tenant/output controls and Bandit; independent assessment pending |
| 19 | Testing | Implemented + verified | Final command/workflow results above; no claim of exhaustive coverage |
| 20 | Accessibility | Partial, automated checks verified | axe/keyboard and responsive Chromium; manual screen-reader and other browsers needed |
| 21 | Monitoring | Implemented; external wiring pending | Protected metrics, structured logs, worker/schema health and alert-rule template; live routing/tracing absent |
| 22 | Backup/restore | Implemented + verified isolated drills | Actual SQLite/PG dump+documents restore, integrity checks and quarantine; cloud disaster recovery pending |
| 23 | Azure | Implemented template; deployment blocked externally | Docker build and Bicep compile; subscription/resource identities/network/DNS access required |
| 24 | CI | Implemented + verified at linked final run | Backend matrix, browser, audits, operational drills, container/IaC; admin-enforced branch gates need repository owner |
| 25 | Documentation | Implemented + reviewed | Setup, environment, API inventory, security/AI/integrations, operations, recovery, acceptance and this report |

## Remaining autonomous work

No known failed automated check or unimplemented core task is intentionally left at this handoff. The next work depends on the external prerequisites below: configure staging, execute enabled live-provider acceptance, run sustained production-shaped load/cloud disaster drills, address findings from independent reviews, and record a release decision. Broader product development remains the advanced future scope explicitly separated below; it is not a reason to call current interfaces complete integrations.

## Genuine external/user blockers

Credentials should be entered directly in Key Vault or the relevant provider console, never pasted into chat, Git or public issues. Nonsecret settings use the runtime environment described in [environment.md](environment.md).

| Needed / why | Where to configure | How to verify | Next engineering action |
|---|---|---|---|
| Azure subscription, authorized deployment access, region/network/resource choices, staging budget and domain ownership; source cannot provision someone else's approved environment | Separate staging resource group, Container Apps environment, PostgreSQL, private Blob, ACR, Key Vault, identity and DNS; IDs in protected Bicep parameters | Run what-if, deploy immutable image, migrate once, verify HTTPS/schema/worker/private storage and negative access tests | Configure supplied resources, deploy staging, exercise smoke/rollback/cloud restore and publish evidence |
| SMTP service and approved sender domain; production recovery requires real delivery | SMTP_HOST/PORT/MAIL_FROM runtime; SMTP_USERNAME/PASSWORD as protected credentials; SPF/DKIM/DMARC in provider/DNS | Deliver verification/reset/security notice, check spam/delay, token expiry/replay and link origin | Wire service, run end-to-end identity acceptance, then allow signup |
| Google OAuth project/consent status, exact redirect, test users and mailbox/calendar authorization | Google Cloud web OAuth application; GOOGLE_CLIENT_ID/REDIRECT_URI runtime, CLIENT_SECRET in Key Vault; account connection through Settings | Grant required scopes; full/incremental sync, revoke/reconnect, approved send/create/update/delete, timezone and recovery cases | Run live integration checklist and fix contract/runtime discrepancies |
| Stripe account, product/price, customer portal and webhook; pricing/cancellation/tax policy belongs to business | Stripe test dashboard; STRIPE_PRICE_ID runtime; API/webhook signing secrets in Key Vault; exact `/api/v1/webhooks/stripe` endpoint | Checkout, payment success/failure, change/cancel, duplicate/out-of-order/replayed event, invoice and entitlement reconciliation | Execute test lifecycle; wire approved commercial policy before enabling live charges |
| AI provider account/key/model access and approved representative evaluation data/budget | AI_PROVIDER/MODEL/TIMEOUT/MONTHLY_LIMIT runtime, AI_API_KEY in Key Vault | Live strict-schema calls and human-scored extraction/answers, cross-tenant/provenance/prompt-injection cases, latency/cost | Run and version live evaluations; tune/fix outputs and thresholds before enablement |
| Licensed MLS provider and rights, API docs, sample payloads and test access; adapters depend on the real contract | Provider console/contract plus Key Vault after provider-specific adapter configuration is defined | Verify field/status/delete mappings, licenses, update cadence, rate limits, reconciliation and tenant separation | Implement the selected adapter and tests; enable monitored polling only after approval |
| Operational policy and ownership: retention/legal holds, support identity recovery, MFA enforcement, recovery budget/objectives and on-call recipients | Approved launch record/runbooks; actual backup/alert services and routing; separate vault key backup | Timed Azure restore meets accepted targets; induced alert reaches owner; support/UAT exercises pass | Apply accepted policy, wire services, run drills and close launch evidence |
| Independent human verification: realtor UAT, assistive technology review, security/AI assessment and data/legal review | Staging access for designated reviewers; private finding tracker and signed release record | Complete real workflows and accessibility/authorization/privacy review; resolve findings | Fix identified issues, rerun regression checks and update readiness report |
| GitHub administration for enforced required checks/reviews and release environment approval | Repository Settings → Rules/Environments; installation tools lack administration writes | Confirm direct unreviewed/unverified production changes are blocked | Verify the configured policy and use it for subsequent releases; never bypass protections |

## Known limitations

- No live Google, OpenAI, Stripe, SMTP, Blob or Azure acceptance was performed. No customer emails, calendar changes or charges were sent as part of this work.
- MFA is opt-in TOTP with recovery codes; organization enforcement/passkeys and verified support recovery require policy/implementation beyond this decision. No security-question bypass exists.
- Tenant isolation relies on audited application scope and relational keys; no database RLS. CRM visibility is organization-wide, not private agent inboxes.
- AI summaries can be wrong despite schema/evidence controls. Offline tests do not measure model accuracy. Proposed facts/actions require review; matching uses declared property preferences, not protected attributes.
- PDF parsing is resource bounded but not antivirus, CDR or a complete sandbox. Scanned OCR/call transcription/telephony are architecture only. Crash-orphan blobs need a quiesced reviewed reconciliation procedure.
- No licensed live MLS feed, market valuation, e-signature, travel routing, recurrence-series editing, learned scoring, exhaustive semantic search or visual workflow builder. These were identified as advanced/future scope; working CSV import and typed workflow rules remain available.
- Source context, exports and batch sizes are intentionally bounded. Listing import protects manual changes with conflicts; there is no automatic overwrite merge.
- External providers and SQL cannot commit atomically. Ambiguous sends are held for reconciliation. Account email may be duplicated after a crash, while tokens remain single use.
- Metrics are per-process counters/basic shared gauges. Alert rules require deployment/routing. There is no distributed tracing integration or demonstrated production SLO.
- Load and recovery evidence uses short fictional workloads. RPO one hour/RTO four hours and suggested retention are proposed targets, not accepted or achieved cloud guarantees. Backups contain private data and need separate encryption/access/key policies.
- Automated Chromium/axe tests do not replace screen readers, other browsers, independent penetration testing or production-shaped concurrency/failure testing. Two upstream Python test-client deprecation warnings remain.

## Final launch checklist

- [x] Preserve and implement the existing architecture and core workflows.
- [x] Version schema changes and verify SQLite/PostgreSQL behavior.
- [x] Implement tenant/RBAC boundaries, recovery/verification/MFA and evidence/approval controls.
- [x] Execute offline AI evaluations, isolated load baseline and verified restore drills.
- [x] Provide metrics/health, worker reliability, deployment artifacts and operator runbooks.
- [x] Audit current base/head, rules and review state before a merge decision.
- [x] Complete application CI (one disclosed browser retry; isolated device suites added for final CI).
- [ ] Confirm final isolated browser run and merge result on PR #1 before release.
- [ ] Provision isolated staging/production resources, DNS/HTTPS and protected secrets.
- [ ] Verify enabled Google/AI/Stripe/SMTP/Blob providers against actual test accounts.
- [ ] Configure live alert routing, automated backups, retention and key recovery; prove Azure RPO/RTO.
- [ ] Approve MFA/support, data retention/privacy, pricing and on-call policies.
- [ ] Complete independent security/AI/manual accessibility review and realtor UAT; resolve findings.
- [ ] Enforce repository/release approval gates and approve a separate production launch.
