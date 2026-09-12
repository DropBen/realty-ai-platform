# Troubleshooting

| Symptom | Check |
|---|---|
| App startup says alembic_version missing | Run migrations against the configured database first |
| Sign-in request is rejected by origin | Match `APP_ORIGIN` exactly to the browser URL and restart the API |
| Mutation says session verification failed | Refresh/sign in to renew the CSRF/session cookie pair |
| Demo account missing | Confirm dedicated demo mode and run `python -m realty.seed` |
| Approved action stays queued | Run the worker with the same database/config; inspect Settings → Activity |
| Action is uncertain | Inspect provider state; do not blindly retry or assume nothing happened |
| Google unconfigured | Demo mode must be false; configure client ID/secret, redirect URI and encryption key |
| Google requires reconnect | Verify scopes/token revocation and reconnect through Settings |
| Imported mail is absent | Import uses a 90-day relevance window; promotions/social and unrelated senders are filtered |
| AI unconfigured | Set provider/key/model in a non-demo environment; structured search still works |
| AI request limit | Check monthly attempted requests and subscription/trial state |
| Billing does not activate after checkout | Confirm a valid signed webhook and the configured price; redirect success is not entitlement |
| PDF says OCR required | The file has no extractable text; an OCR implementation must be configured separately |
| Frontend source loads but page is blank | Check build artifacts and CSP; rebuild then restart the API |
| Vite/esbuild spawn EPERM on Windows | Use `node scripts/build.mjs` and the built single-origin API preview |
| Headless browser IPC fails | Run the supplied Playwright suite on a host with working browser IPC, such as Linux CI |
| Docker command cannot reach daemon | Start Docker Desktop or use the native local path |

Logs use safe error codes. Never paste tokens, passwords, OAuth callback query strings or complete customer email into public issues. Include a request/job ID and the failing workflow instead.
