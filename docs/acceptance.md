# Acceptance and implementation state

The [completion report](completion-report.md) contains the 25-area verification matrix, scores, genuine external blockers and launch checklist. The [verification record](verification.md) distinguishes executed checks from configured workflows. This application is ready for staged acceptance after those checks pass; it is not declared production-ready.

## Core behavior implemented

- CRM, relationship profiles, source facts, confirmed preferences, activity history, deals/transaction milestones, tasks, appointments, matching, daily briefing and bounded structured search.
- Email verification/password recovery, optional TOTP/recovery codes, session control, central roles, tenant scope, CSRF/origin checks and database rate limits.
- Review/edit/approve/reject/snooze/schedule actions, version/hash approval snapshots, worker reauthorization, guarded internal undo and explicit uncertain external states.
- Gmail/Calendar OAuth and provider adapters; source-linked commitment review, ownership/deadlines and deduplicated reminders; DST/all-day calendar imports and conflicts.
- Reviewed CSV/JSON listing ingestion; document extraction/classification/entity proposals with evidence and classification review; authenticated storage and durable deletion cleanup.
- Stripe signed lifecycle/webhook handling, usage reservations, typed workflows, renewable/fenced jobs, operational metrics/health, recovery tooling and automated verification.

## Implemented but not live verified

Google consent, mailbox reads/sends, Calendar mutations; OpenAI model calls/quality; SMTP deliverability; Stripe checkout/portal/subscription lifecycle against an actual account; Azure Blob, network, managed database, Key Vault, monitoring and deployed Container Apps. Contract tests and valid configuration are necessary but insufficient evidence for these services.

## Explicit launch limitations and future scope

TOTP is opt-in, not organization-enforced or phishing-resistant. PostgreSQL RLS is not enabled; application scoping and composite keys are tested. Documents use isolated bounded parsing, not antivirus; scanned OCR and telephony/transcription remain provider interfaces. ML lead scoring, exhaustive semantic search, automatic relative-date interpretation, travel-time routing, recurrence-series editing, e-signatures, visual workflow editing and a licensed live MLS adapter remain future scope from the directive. CSV/JSON import is working; it is not advertised as MLS connectivity.

Profile context is intentionally bounded. Listing conflicts protect manual edits and require reconciliation. Teams share organization-level CRM/mail visibility. Large exports over 20,000 rows/table require an operator-assisted job. Business retention/legal holds, enforcement of MFA and independent reviews require explicit launch policy. Metrics are basic process counters and queue gauges, not distributed traces. Short 3-user load tests do not certify production capacity. Recovery drills use small fictional datasets, not Azure disaster scenarios.

## Release gates

Pass the complete final CI; verify the repository merge state; deploy an immutable image to isolated staging; exercise all enabled providers; configure and test actual alerts/backups/restore; obtain security, accessibility and realtor UAT acceptance; approve retention, support, pricing and recovery objectives. Then make a separate production release decision. A Git merge does not publish the service or satisfy those operational gates.
