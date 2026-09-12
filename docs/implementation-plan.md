# Implementation plan and acceptance contract

Build a modular monolith with a separate durable worker. Every milestone must have executable behavior, validation, and honest integration status.

1. Foundation: relational migrations, organization membership, password sessions, CSRF, centralized permissions, tenant isolation.
2. CRM: contacts and buyer/seller preferences, properties, deals, tasks, commitments, calendar, communications, timeline and documents.
3. Intelligence: data-derived briefing, structured search, explainable matching, source-backed extraction, bounded provider interface, meeting preparation.
4. Actions: propose, edit, approve, snooze, reject, execute, audit, recover and undo internal mutations. External side effects always require specific approval.
5. Integrations: Google OAuth/refresh/revoke, Gmail and Calendar cursor sync, Stripe verified webhooks and customer portal, document storage.
6. Operations: idempotent database jobs, workflow rules, usage limits, notifications, observability, export and account deletion.
7. Experience: consistent responsive application, full navigation, editable forms, actionable empty/error states, accessible controls, keyboard palette.
8. Delivery: automated security/service/API/E2E checks, production build, Docker, Azure IaC, setup/operations guides and acceptance evidence.

Release claims are recorded in `docs/acceptance.md`. Provider sandbox contracts are separate from live-provider certification. No production deployment is implicit in this build.
