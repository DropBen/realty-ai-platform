# Database

The initial Alembic migration contains the concrete schema; it does not dynamically import future model definitions. SQLAlchemy models map typed columns, indexes, timestamps, check constraints, unique keys and relational associations. JSON is reserved for variable action payloads, feature lists, provider metadata and structured event details.

Tenant tables cover memberships, contacts, preferences, properties, deals, transaction milestones, activities, tasks, appointments, communications, facts, commitments, actions, notifications, documents, integrations, cursors, subscriptions, usage, jobs, workflows and audit events. Organizations/users/sessions/OAuth state/rate buckets/webhook IDs form the identity and operational layer. Leads, buyers and sellers are contact roles rather than duplicated identities. Notes/calls/showings/feedback are typed activities.

Composite `(org_id, id)` keys and foreign keys protect contact/property/deal relationships. Tenant queries are automatically constrained through scoped sessions, with write guards and explicit reference checks at service boundaries. A user has organization memberships rather than a global role.

```sh
python -m alembic upgrade head
python -m alembic check
python -m alembic revision --autogenerate -m "Describe the schema change"
```

Inspect generated migrations, test upgrade/downgrade on disposable data, and use expand/contract changes for live deployments. Never run `Base.metadata.create_all()` instead of migrations in production; it is used only by isolated test fixtures.

Store UTC timestamps without timezone in SQL, normalize aware API input to UTC, and format dates for the user. Daily briefing uses organization-local day boundaries. SQLite uses foreign_keys and WAL. Production requires PostgreSQL and a least-privilege application login, encrypted connections, managed backups and tested restore procedures. Test suites support both engines through `TEST_DATABASE_URL`; local execution evidence is documented separately.

Contact archival is supported without losing history. Document/organization deletion is explicit. Audit tables are append-only by API design, not cryptographically immutable. A regulated archival/retention product would require additional storage and policy controls.

Earlier migration `2375a43c78e9` adds listing import metadata, calendar timezone/recurrence fields, commitment provenance/version, reviewed document analysis, expiring rate buckets, worker pulses and durable global storage cleanup. Identity migration `35b63b33b85a` adds verified-email state, encrypted MFA enrollment/secrets, one-use tokens/recovery codes and encrypted account mail. Existing users are not silently marked verified. API/worker readiness checks the exact head before work. Snapshot/restore and encryption-key requirements are in [backup-restore.md](backup-restore.md).

## Authority migration: 6bda8c204a71

Adds workspace binding to OAuth state, reviewed-value JSON to CRM approvals and durable checkout-attempt JSON to subscriptions. Upgrade invalidates outstanding ten-minute OAuth requests and returns previously approved CRM updates to pending with a new version; historical completed actions remain unchanged. No prior reviewed baseline is invented. Checkout state is excluded from API/export serializers.

Stop API and worker before upgrading this schema, then restart both on the new revision. An isolated migration regression seeds actual prior-schema OAuth/approval/history rows, checks their safe conversion and runs downgrade/upgrade/drift checks. Downgrade also invalidates affected approvals; it is a test/rollback mechanism, not a production data-recovery strategy.
