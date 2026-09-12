# Environment reference

Copy `.env.example` to an ignored `.env` for local development. Production values belong in Container Apps configuration; **secret** values below belong in Key Vault, mapped through `secretReferences` and `secretEnvironment` in `infra/apps.bicep`. Nonsecret values use `runtimeEnvironment`. Never commit real parameters or print secrets. API and worker must use the same settings and encryption key.

| Variable | Default/example and purpose | Required when | Secret |
|---|---|---|---|
| APP_ENV | `development`; use `production` for startup guards/API docs disabled | All | No |
| DEMO_MODE | `true`; fictional data and no external providers | Must be `false` for real data/staging/production | No |
| DATABASE_URL | `sqlite:///./data/realty-demo.db`; production `postgresql+psycopg://USER:PASSWORD@HOST/realty?sslmode=require` | All; TLS/least-privilege production user | Yes |
| APP_ORIGIN | `http://localhost:5173`; built preview `http://localhost:8000`; production `https://app.your-domain` | Exact browser origin for CSRF and account links | No |
| API_ORIGIN | `http://localhost:8000` | Public API origin in deployment configuration | No |
| COOKIE_SECURE | `false` | Must be `true` with production HTTPS | No |
| SESSION_HOURS | `12`, absolute lifetime | Default sufficient locally; approve production policy | No |
| REQUIRE_EMAIL_VERIFICATION | `false` locally | Must be `true` in production | No |
| ENCRYPTION_KEY | Empty; generate Fernet key | Google, MFA, account email, production | Yes |
| MAIL_BACKEND | `disabled`, `outbox` or `smtp` | Production requires `smtp`; outbox is local files only | No |
| MAIL_FROM | `RealtyAI <noreply@example.com>` placeholder | Verified non-example sender in production | No |
| SMTP_HOST | Empty, use chosen provider's hostname | SMTP | No |
| SMTP_PORT | `587` | SMTP STARTTLS endpoint | No |
| SMTP_USERNAME | Empty, provider login | If required by provider | Yes |
| SMTP_PASSWORD | Empty, provider credential | If required by provider | Yes |
| SMTP_STARTTLS | `true`; certificate-verified TLS | Required in production | No |
| MAIL_OUTBOX_PATH | `./data/account-mail` | Local outbox tests only, never public static storage | No |
| GOOGLE_CLIENT_ID | Empty, OAuth web client ID | Google connection | No |
| GOOGLE_CLIENT_SECRET | Empty | Google connection | Yes |
| GOOGLE_REDIRECT_URI | `http://localhost:8000/api/v1/integrations/google/callback` | Exact URI registered in Google Cloud; HTTPS staging/production | No |
| AI_PROVIDER | `disabled` or `openai` | `openai` for model-backed features; demo requires disabled | No |
| AI_API_KEY | Empty | Configured provider | Yes |
| AI_MODEL | `gpt-4.1-mini`, configurable model ID | Confirm provider account access and evaluation quality | No |
| AI_TIMEOUT_SECONDS | `30` | Model deadline | No |
| AI_MONTHLY_LIMIT | `1000` attempted calls per workspace | Quota/cost policy | No |
| STRIPE_SECRET_KEY | Empty, test-mode key in staging | Billing | Yes |
| STRIPE_WEBHOOK_SECRET | Empty, signing secret for exact endpoint | Billing event validation | Yes |
| STRIPE_PRICE_ID | Empty, actual recurring price ID | Billing checkout/entitlements | No |
| STORAGE_BACKEND | `local` or `azure` | Bicep configures `azure` | No |
| STORAGE_PATH | `./data/documents`, outside public root | Local development/recovery | No |
| STORAGE_CONNECTION_STRING | Empty | Azure Blob; least-privilege protected credential | Yes |
| STORAGE_CONTAINER | `documents` | Existing private Blob container | No |
| LOG_LEVEL | `INFO` | Structured logs | No |
| METRICS_TOKEN | Empty disables operator endpoint | Protected scraper; random high-entropy token | Yes |
| TEST_DATABASE_URL | Disposable SQLite/PG | Backend test suite; tables are destroyed | Yes |
| E2E_BASE_URL | `http://localhost:8000` | Disposable demo browser-test application | No |
| DRILL_DATABASE_URL | Empty, DB name `realty_drill_*` | PostgreSQL recovery drill, empty database | Yes |
| RESTORE_DATABASE_URL | Empty, separate empty PostgreSQL DB | PostgreSQL restore; drill name `realty_drill_*` | Yes |
| LOAD_DATABASE_URL | Empty, DB name `realty_load_*` | PostgreSQL load baseline, empty database | Yes |
| PG_BIN_DIR | Unset uses PATH | Optional path to matching PostgreSQL CLI tools | No |

Generate `ENCRYPTION_KEY` with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` directly in a protected terminal and store it in Key Vault. It protects Google tokens, TOTP enrollment/secrets and queued account mail. Retain the matching key for backups. Replacing it without re-encrypting existing data breaks decryption; see [operations](operations.md).

Production startup rejects demo mode, insecure cookies, absent/invalid encryption, SQLite, non-HTTPS browser origin, disabled email verification, non-SMTP mail, missing host, absent STARTTLS and an example sender. Missing optional providers fail explicitly when invoked. Guards do not prove DNS ownership, TLS connectivity, deliverability, private networking, provider scopes or operational policy; those need staging validation.

## Validated configuration

`APP_ENV` accepts only `development`, `test`, `staging`, or `production`. Both staging and production enforce the deployed security guards, including HTTPS for APP_ORIGIN and API_ORIGIN. Origins may not contain credentials, paths, queries or fragments; a trailing slash is normalized. Unknown AI/storage/mail backend names and logging levels fail startup. Session lifetime is 1–168 hours, AI timeout 1–120 seconds, monthly allowance nonnegative, SMTP port 1–65535. Validation error text omits input values to avoid printing secrets.

Turning off DEMO_MODE does not promote existing demo tenants. Their stored `is_demo` flag continues to block external Google/AI/billing/SMTP operations and keeps demo labels visible. Create a separate non-demo database/workspace for integration acceptance.
