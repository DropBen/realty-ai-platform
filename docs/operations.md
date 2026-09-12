# Operations and incident runbook

Run the API and worker as separate services from the same immutable image. PostgreSQL is required outside development; SQLite supports one development worker. Keep staging and production databases, storage containers, provider apps, secrets and ingress independent.

## Health, metrics and alerts

- `/health/live`: process available. `/health/ready`: database reachable **and** Alembic revision equals the application head. A mismatched schema refuses readiness and worker startup.
- Settings → Activity exposes workspace queue counts, oldest due age, recent worker heartbeat, schema and failed storage cleanup to owners/admins. Worker availability is shared infrastructure status; customer job counts remain tenant scoped.
- `/internal/metrics` requires `Authorization: Bearer <METRICS_TOKEN>`. Inject a random secret in the scraper and Key Vault; do not put it in a URL. Missing configuration returns 503, wrong token 403. Restrict ingress to the monitoring network as well.
- Counters: `realty_http_requests_total{method,status}`, `realty_http_duration_seconds_total{method,status}`. Gauges: `realty_worker_available`, `realty_queue_oldest_due_seconds`, `realty_jobs{status}`. HTTP counters are per process and reset on restart; scrape each replica. Queue gauges describe the shared database, so use `max` rather than summing replicas. There are no customer IDs or message contents in metric labels. Duration totals support averages, not percentile calculations.
- `infra/alerts.rules.yml` supplies starter Prometheus alert rules. Load and validate them in the chosen monitoring service, configure real delivery/on-call ownership, and induce a staging failure. Source files alone do not mean alerting is active. Use logs or Azure platform metrics for latency percentiles, resource saturation and database/storage errors.

Structured logs include UTC timestamps, request/job IDs, stable codes and durations. Request bodies, query strings, credentials and provider payloads are excluded. Request IDs connect a support error to logs. Audit records track actor/tenant/action/target; they are append-only through the API, not immutable evidence against a privileged database operator. Distributed tracing and an external error tracker are not integrated.

## Worker stalled, retries and dead jobs

1. Check database/schema readiness, replica health and heartbeat (unavailable after 90 seconds). Review oldest due age and `job.failed` codes.
2. Fix the dependency, credentials or schema before retrying. GET provider reads have bounded transport retries; jobs use exponential delays and normally stop after five attempts.
3. Admin retry preserves the monotonic attempt number and grants one more operator attempt. It never resets the fencing epoch. A PostgreSQL heartbeat renews each ten-minute lease every 30 seconds; before-flush/commit checks prevent a superseded worker from committing business changes.
4. `external_uncertain`, interrupted execution and restored external work require provider reconciliation. Search the authorized mailbox/calendar using the action/provider identifiers. Never blindly retry a send. Record the result, then create a fresh proposal if a new operation is required.
5. Restart a stopped worker only after checking these states. A crash can duplicate account-notice mail after SMTP acceptance, but recovery/verification tokens remain single use. No exactly-once external delivery guarantee is made.

## Provider incidents

Google: verify consent, granted scopes, refresh-token validity and the connected owner. Reconnect after revocation; inspect queued/dead job codes and resync. Expired Gmail/Calendar cursors fall back to full synchronization; records have provider deduplication keys. Imports checkpoint between bounded provider reads, and advance cursors only after completion. Imported calendar data may reveal conflicts that changed outside this application.

AI: missing configuration, invalid schema/evidence or exhausted quota must remain visible. Invalid output is not repeatedly billed by job retries. Quota reservation counts attempts before transport, including timeouts; use usage records to reconcile charges. Disable the provider if quality fails. Summaries are review material, not certified facts.

Stripe: compare the signed event and canonical subscription/customer/price state. Duplicate receipts do not duplicate changes. Correct the configuration and resend the legitimate event from Stripe; do not edit client plan state or invent paid entitlements. Follow `billing.md` for live test-mode acceptance.

SMTP: inspect account-mail jobs and sender verification; never log decrypted bodies or token links. Fix service/TLS credentials and retry. Verify email arrives and the link is single use before enabling public signup.

## Data retention, deletion and keys

Maintenance removes expired sessions/OAuth state, expired rate buckets, auth tokens older than expiry + one day, account-mail rows after seven days and old worker pulses. Successful mail bodies are cleared immediately. Confirmed commitments generate version-specific due reminders. Business records, communications, audits, jobs and usage have no automatic age-based purge: retention, legal holds and support policy require an approved business decision. Do not improvise destructive retention.

Document deletion is queued in the database transaction; the worker deletes the blob only after commit. Organization deletion preserves those cleanup records until storage removal succeeds. Cleanup retries up to five times with backoff; investigate persistent failures in Settings. A process/power failure between an upload and database commit can still leave an orphan. Reconcile the storage inventory against database document keys during a quiesced maintenance window, using a grace period and reviewed dry-run list. Never delete recent unmatched uploads automatically.

Fernet protects Google tokens, TOTP secrets/pending enrollment and queued account mail. Back up the encryption key separately in an access-controlled vault; losing it prevents decrypting existing values. Use the tested [transactional rotation procedure](review-failure-audit.md), including dry-run validation, maintenance freeze and atomic configuration cutover. Never replace a key in place or disable MFA merely because a key was lost.

## Recovery and release ownership

Use [backup and restore](backup-restore.md). Proposed initial recovery objectives are **RPO ≤ 1 hour, RTO ≤ 4 hours**, subject to business approval and a timed Azure staging exercise. These are targets, not achieved cloud guarantees. A small local drill cannot establish them. Assign an on-call owner, release approver and incident communications channel before launch. A rollback of application code does not roll back SQL or external sends; use compatible migrations and a separately approved recovery plan.
