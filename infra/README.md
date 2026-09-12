# Azure application deployment

`apps.bicep` deploys the immutable application image twice: web/API with HTTPS ingress and a worker without ingress. It references an existing Azure foundation rather than assuming subscription/networking policy.

Provision separately in the chosen subscription:

- A Container Apps environment with Log Analytics and VNet integration.
- Azure Database for PostgreSQL Flexible Server (16+), private network access, TLS required, automated backups and a tested recovery policy.
- A private Blob Storage container and private endpoints reachable by the environment.
- Azure Container Registry and a user-assigned identity with AcrPull.
- Key Vault, secret versions, private connectivity, and least-privilege identity access.
- DNS, TLS, ingress request limits, rate-limit protection and monitoring alerts.

Pass Key Vault secret references for `DATABASE_URL`, `ENCRYPTION_KEY`, `STORAGE_CONNECTION_STRING`, and any configured Google, AI, Stripe secrets. The database URL must use the form `postgresql+psycopg://USER:PASSWORD@HOST/realty?sslmode=require`. The image's production configuration refuses demo mode, insecure cookies or SQLite.

Compile and preview without deploying:

```sh
az bicep build --file infra/apps.bicep
az deployment group what-if --resource-group <staging-resource-group> --template-file infra/apps.bicep --parameters @staging.parameters.json
```

Run `python -m alembic upgrade head` in a single controlled migration job against staging before rolling out the application. This repository does not run production migrations from every API replica. After staging verification and an approved release, deploy the same image digest to production.

The Bicep template compiled successfully with Bicep CLI 0.47.16. It has not been validated against a real subscription or deployed. Cloud credentials and foundation resource IDs are intentionally absent. Do not interpret syntax validation as a successful Azure deployment.
