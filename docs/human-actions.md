# Human action required: next validation gate

Only the two items below are needed for the next live workflow validation. Azure, Stripe, SMTP, production DNS and merge authorization are separate later gates; they do not block this local acceptance exercise. Do not send secrets in chat or commit them.

An ignored .env.acceptance and empty data/realty-acceptance.db have already been prepared in the working checkout. They use separate document storage, account-mail outbox and encryption key. The acceptance origin is http://127.0.0.1:8001; the demo remains on http://localhost:8000. Different hosts avoid sharing browser cookies. The private profile is intentionally excluded from the source archive.

## 1. Google test integration

**Provide:** Google Cloud OAuth Web Application Client ID and Client Secret, plus a designated test Google account/mailbox/calendar and consent from its owner. If you instead grant project access with permission to enable APIs and manage OAuth clients, the engineer can perform that configuration.

**Why:** Automated HTTP contracts cannot prove Google's actual consent, refresh, synchronization, delivery or conditional Calendar behavior.

**Unlocks:** Live OAuth, Gmail ingestion and approved send, Calendar synchronization and revision-conflict validation, reconnect and retry checks.

**Blocks:** Google acceptance and the live end-to-end realtor workflow. It does not block standalone AI evaluation or the existing demo.

**Configure:** In a project you control, enable Gmail API and Google Calendar API. Configure OAuth consent for testing, list the designated account as a test user, and create a Web Application client. Register exactly http://127.0.0.1:8001/api/v1/integrations/google/callback as its redirect URI. This local callback follows [Google's Web Server OAuth rules](https://developers.google.com/identity/protocols/oauth2/web-server). Place GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in the ignored repository-root .env.acceptance, or provide the location of a protected downloaded credential file so the engineer can load it. Do not alter the prepared encryption key or demo profile.

**Immediately afterward:** The engineer starts the isolated API/worker, verifies the profile and opens the connection flow. The account owner completes Google consent. After permission for the designated test mailbox/calendar is confirmed, the engineer runs the recorded read/extract/review/edit/reject/approve/execute/audit/timeline acceptance, including refresh, duplicate ingestion and changed-event conflicts. Only test messages/events are used.

## 2. Live AI validation

**Provide:** An OpenAI project API key with access to the configured model and authorization for a small paid evaluation run. An explicit spending ceiling is a business authorization, not an architecture decision.

**Why:** Offline evidence fixtures and mocked structured responses do not establish real model accuracy, latency, cost or injection resistance.

**Unlocks:** Live extraction/provenance and adversarial evaluation, followed by the understanding/recommendation portion of the Google workflow.

**Blocks:** Real model evaluation and the AI portion of the full workflow. It does not block standalone Google OAuth/sync/manual-review checks.

**Configure:** Put AI_API_KEY in the same ignored .env.acceptance or provide its protected secret location. The engineer sets AI_PROVIDER=openai, verifies model access and applies the authorized budget. The prepared profile limits AI_MONTHLY_LIMIT to 20 attempts initially; a request cap is not a monetary guarantee.

**Immediately afterward:** The engineer runs the existing fictional/adversarial source corpus against the real adapter, records accuracy/error/latency/token results, fixes discrepancies, then executes the combined workflow with the designated Google test account.

## Later release gates

Production still requires staged PostgreSQL/Blob/runtime validation, actual account-email delivery, billing acceptance if billing is enabled, cloud load/recovery/alert delivery, and operational/legal/user acceptance. Full long-term prerequisites remain in project-status.md. No production launch or default-branch merge is implied by supplying these test credentials.
