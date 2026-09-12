# Review and failure-boundary audit

September 12, 2026. This continuation fixes demonstrated defects in the existing core workflow without adding services or runtime dependencies.

## Decisions and verified behavior

- Reviewers can withdraw or edit a queued approval until execution starts. A conditional update binds status/version; editing clears authority. Workers claim the exact reviewed version, actor and digest, and obsolete deliveries cannot invalidate newer reviews.
- Action payloads, nested calendar events, appointments and timeline records resolve to the same tenant-owned contact. Missing optional payload references inherit the selected contact.
- Email analysis reserves provider usage before HTTP, then conditionally claims the unchanged source in the transaction that records facts, commitments and processing usage. Overlapping calls may consume two provider attempts, but only one records the result. Duplicate AI fields reject the entire extraction; repeated commitment quotes are coalesced.
- Calendar change approvals contain the local event and imported ETag. Google writes carry If-Match, so a local change or Google 412 requires synchronization and fresh review. Unversioned imports must be synchronized before modification. This follows [Google's versioning contract](https://developers.google.com/workspace/calendar/api/guides/version-resources); HTTP tests simulate it and do not establish live acceptance.
- A database partial unique index coalesces active manual/scheduled sync jobs by organization, account, resource and calendar. Different resources remain independent; completed jobs allow later synchronization. Existing renewable leases and cursor checkpoints remain authoritative.
- Commitment reviews use conditional versions on both databases. Slow document storage runs in the API thread pool; a test holds an upload open while checking liveness on the same event loop.
- Browser requests propagate cancellation, handle malformed cookies and proxy HTML, preserve safe error codes and backoff, and retry transient GET failures at most once. Mutations are never retried automatically. Date formatting recognizes positive and negative offsets.
- Email drafts use labelled recipient/subject/message fields. Failed edits remain open. Only one review/editor dialog is open at a time. Browser tests exercise withdrawal, editing with axe, and recovery from a 503 HTML error.

## Migration 9f24a781c6de

Stop API and worker and take a verified backup before upgrading. The migration adds event ETags, widens composite calendar IDs to 1,536 characters and reserves active sync resources. Historical approved Calendar updates/deletes return to pending with a new version; completed history remains. Existing duplicate active read-sync jobs are coalesced onto their oldest reservation and shared import cursor.

SQLite table recreation explicitly preserves the event end-after-start constraint. A regression attempts an invalid update after upgrade and downgrade. Downgrade retains the wider identity column to avoid truncation; it removes revision/reservation metadata and invalidates affected approvals. Use backups for recovery.

## Quiesced encryption-key rotation

The command covers Google tokens, active/pending TOTP secrets and queued account mail across all organizations. No HTTP endpoint exposes it.

1. Stop every API/worker process and take a verified backup. Keep the current ENCRYPTION_KEY in the maintenance environment.
2. Generate a replacement Fernet key in a protected terminal/secret manager and set ROTATION_NEW_KEY in the maintenance process environment. Keep key values out of arguments, logs, chat and Git.
3. Run python -m realty.key_rotation. The dry run validates all populated encrypted fields and reports counts only.
4. Run python -m realty.key_rotation --apply --quiesced. A corrupt value or detected racing writer rolls back the entire transaction. Repeating it skips values already encrypted with the replacement key. Plaintext and Fernet timestamps are preserved.
5. Before restarting, update the shared ENCRYPTION_KEY to the replacement, remove ROTATION_NEW_KEY from the maintenance environment, then start API/worker and verify readiness, MFA and provider access. If configuration cannot be updated, keep services stopped and reverse the rotation with the protected keys.
6. Retain the old protected key for matching historical backups until their approved retention expires.

This requires a maintenance outage and the current key; it cannot recover a lost key. Automated fixtures never rotate an existing demo or production key.

## Validation

The initial nine review regression cases produced eight failures before fixes. The local suite then passed 191 cases with three PostgreSQL-only skips; three additional key-rotation cases passed separately. All 12 frontend transport tests passed. Final combined CI and operational evidence is recorded in project-status.md and verification.md. Live provider, cloud and realtor acceptance remain separate gates.
