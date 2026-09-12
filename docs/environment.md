# Environment reference

Copy `.env.example` to `.env`; the file is ignored by Git. No real credentials are included.

| Variable | Default / purpose |
|---|---|
| `APP_ENV` | `development`; production enables startup guards and hides API docs |
| `DEMO_MODE` | `true`; must be false for all live providers and real customer data |
| `DATABASE_URL` | Dedicated SQLite demo DB; PostgreSQL with TLS in production |
| `APP_ORIGIN` | Exact browser origin for CORS/CSRF; localhost:5173 for Vite or localhost:8000 for built preview |
| `API_ORIGIN` | Public API origin for deployment configuration |
| `COOKIE_SECURE` | False locally; must be true over production HTTPS |
| `SESSION_HOURS` | 12-hour absolute server-session lifetime |
| `ENCRYPTION_KEY` | Fernet key protecting Google tokens; required for live Google and production |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | OAuth web application credentials |
| `GOOGLE_REDIRECT_URI` | Exact registered `/api/v1/integrations/google/callback` URL |
| `AI_PROVIDER` | `disabled` or `openai`; demo requires disabled |
| `AI_API_KEY` | Server-only provider credential |
| `AI_MODEL` | Configurable structured-output model; default `gpt-4.1-mini` |
| `AI_TIMEOUT_SECONDS` | 30-second model-call deadline |
| `AI_MONTHLY_LIMIT` | 1000 attempted requests per organization/month |
| `STRIPE_SECRET_KEY` | Server Stripe key; use test mode in staging |
| `STRIPE_WEBHOOK_SECRET` | Webhook signing secret from the exact endpoint |
| `STRIPE_PRICE_ID` | Recognized recurring price; provider state controls entitlements |
| `STORAGE_BACKEND` | `local` for development or `azure` |
| `STORAGE_PATH` | Local document directory; not a public static root |
| `STORAGE_CONNECTION_STRING` | Azure Blob credential; inject from Key Vault |
| `STORAGE_CONTAINER` | Existing private Blob container, default `documents` |
| `LOG_LEVEL` | Application structured-log level, default INFO |
| `TEST_DATABASE_URL` | Optional disposable integration-test database; never customer data |
| `E2E_BASE_URL` | Optional isolated test application URL, default localhost:8000 |

Generate an encryption key with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` and put it directly into the protected environment. Do not paste it into issues, commits or logs. Rotation currently requires controlled token re-encryption or reconnecting Google accounts; replacing the key without migrating ciphertext breaks refresh.

Production startup rejects demo mode, insecure cookies, absent encryption, non-HTTPS origin and SQLite. Other missing providers return an explicit unconfigured response when invoked.
