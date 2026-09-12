# Backup, restore and disaster recovery

`scripts/backup_restore.py` creates a **quiesced** database-plus-document snapshot and restores into a new directory and, for PostgreSQL, a separately created empty database. It never overwrites an existing restore directory. Run from the repository root with Python dependencies installed and `PYTHONPATH=backend` (or the editable package installed). Use a protected operator host with database and Blob connectivity. PostgreSQL requires matching or newer `pg_dump`/`pg_restore` tools; `PG_BIN_DIR` may point to their directory.

## Take and verify a snapshot

1. Pause API writes and workers. The `--quiesced` flag confirms you did this; it does not freeze the service. A database-only snapshot cannot atomically capture object storage. Keep the source quiesced until both copies and verification complete.
2. Configure source `DATABASE_URL`, `STORAGE_BACKEND`, `STORAGE_PATH` or Azure connection/container settings in the protected environment. Never pass a database password on a command line.
3. Run:

```sh
python scripts/backup_restore.py backup --destination /protected-backups/release-snapshot --quiesced
python scripts/backup_restore.py verify --source /protected-backups/release-snapshot
```

SQLite uses its online backup API. PostgreSQL uses a custom-format dump with credentials supplied through environment variables. Every database/document file has a SHA-256 checksum; document bytes must also match the authoritative database hash. The manifest records schema revision and row counts before/after the copy. Row-count comparison is not a substitute for quiescence: in-place changes could leave counts unchanged.

Snapshot files contain private data, encrypted provider tokens and password hashes. Store them on encrypted, access-controlled storage and in a separate failure domain; retain access logs and approved retention. Checksums detect corruption, not malicious replacement of both files and manifest. Only restore trusted operator-created snapshots. Keep a protected copy of the corresponding Fernet key separately.

## Restore into isolation

For PostgreSQL, create a fresh empty database with an operator-approved name and set `RESTORE_DATABASE_URL` in the environment. Keep provider/network egress disabled on the restored application until reconciliation.

```sh
python scripts/backup_restore.py restore --source /protected-backups/release-snapshot --destination /recovery/new-copy
```

The restore verifies checksums, row counts, schema, document hashes and SQLite foreign keys. It invalidates sessions, OAuth state and account tokens; removes queued mail bodies; cancels token-delivery jobs; and puts approved actions back into review. Previously executing external actions become **uncertain**. Their jobs are stopped. This prevents recovery from silently replaying approved external work. Users must sign in again; workers must not resume until an operator reviews recovered jobs and integration synchronization state.

Restored documents are written to `new-copy/documents` even when the source was Azure. Before a cloud cutover, upload those verified keys into a **fresh private** recovery container, verify hashes again, and configure the restored application for it. The CLI does not overwrite the production Blob container or configure Azure point-in-time recovery.

Check readiness against the matching application version, verify tenant separation and representative records/files, reconcile provider activity after snapshot time, verify delivery and billing state, then obtain the release decision before switching DNS/traffic. Preserve the failed environment and evidence for investigation. Do not run destructive down migrations to simulate a production rollback.

## Reproducible drills

The following create only fictional users, two tenants, documents, sessions and queued actions. They test isolation, token revocation, action quarantine, rejection of an existing target and checksum corruption. Scratch directories receive unique names.

```sh
python scripts/recovery_drill.py --work-dir work --output docs/evidence/recovery-sqlite.json
python scripts/recovery_drill.py --postgres --work-dir work --output docs/evidence/recovery-postgres.json
```

PostgreSQL drill requires **empty dedicated** `DRILL_DATABASE_URL` and `RESTORE_DATABASE_URL`, whose names start `realty_drill_`. CI provisions both independently. Do not use customer databases. See [verification](verification.md) for executed results; a configured command is not evidence of a completed drill.

## Proposed launch policy

Pending business acceptance: RPO one hour, RTO four hours; managed PostgreSQL point-in-time backups plus protected Blob versioning/soft delete, weekly consistency snapshots, 30-day retention, and a quarterly timed restore into isolated staging. Choose region/redundancy/retention based on the actual contract and budget. Prove recovery from lost database, lost blob and compromised credentials, including key restoration and uncertain sends. Live Azure backups, off-site copies, alert delivery and achieved RPO/RTO remain unverified until that exercise is completed.
