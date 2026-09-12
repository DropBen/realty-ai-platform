# Deployment and operations

The build creates one immutable image containing the API and compiled web assets. Run it as two processes/services: API and worker. PostgreSQL and Azure Blob are managed separately. No production deployment is performed by a branch push; `.github/workflows/ci.yml` only verifies.

## Environments

Local → development → staging → production, each with independent databases, secrets, provider apps, webhook endpoints and document containers. Production uses HTTPS, `DEMO_MODE=false`, secure cookies, a valid Fernet key, PostgreSQL TLS and private object storage. Set `APP_ORIGIN` to the exact public origin.

Use `infra/apps.bicep` with preprovisioned network/identity/storage/database resources as described in `infra/README.md`. It deploys the app and a non-ingress worker and references Key Vault secrets. Bicep compilation and the Docker image build pass in Linux CI. Azure provisioning and runtime acceptance still require a subscription and a staging deployment; neither was executed.

## Release sequence

1. Pass formatting, lint, types, unit/API/security/provider tests, PostgreSQL tests, browser tests, dependency audit and container build.
2. Build/push an image identified by digest. Generate a release record and back up the database.
3. Run a single authorized migration job in staging; seed only dedicated demo environments.
4. Deploy staging, exercise live test-mode Google/Stripe/AI journeys, and verify monitoring and restoration.
5. Approve production release through a protected environment. Deploy the same digest, migrate with an operator-reviewed plan, verify health and smoke-test authorized workflows.
6. Roll back the application revision if needed; use backward-compatible schema changes. Restore data only through a separate recovery procedure.

## Monitoring

`/health/live` reports process availability; `/health/ready` checks database connectivity. Structured JSON request logs contain request ID, status and duration. Worker logs use job/tenant IDs and stable failure codes. Audit, integration last-sync fields, usage records and Settings → Activity provide application diagnostics.

Alert on sustained API failures, database connectivity, dead jobs, delayed queued jobs, uncertain external actions and failed Google refresh. Export logs to Azure Log Analytics and add Application Insights/metrics as part of deployment wiring. A dedicated metrics exporter and distributed traces are not included.

Start with one worker. Job leases last ten minutes; expensive imports may exceed that window and need operational limits or lease renewal before multi-worker scale. Keep PDF workers memory/CPU bounded and restrict egress. Reconcile uncertain external actions directly against the provider before creating another approval.

Record RPO/RTO, backup retention, storage lifecycle and restore evidence before accepting customers. These operational properties cannot be established by source code alone.
