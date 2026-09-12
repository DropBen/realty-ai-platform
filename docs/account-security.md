# Account security and recovery

The identity layer now implements email verification, password recovery/change, session listing/revocation, logout from all devices, TOTP enrollment/login/disable and recovery-code replacement. These are executable account workflows, separate from tenant CRM authorization. TOTP is optional for each account in this initial release; it is not phishing-resistant. Enterprise enforced MFA and passkeys remain future policy work.

## Local configuration

Set `ENCRYPTION_KEY` to a generated Fernet key and `MAIL_BACKEND=outbox`. The worker writes account messages to `MAIL_OUTBOX_PATH` (default `data/account-mail`), which is ignored by Git and never served over HTTP. Read the `.eml` file locally to exercise verification/recovery. This is explicitly local delivery, not an SMTP test. Use an isolated demo database; do not put customer identities in a shared development outbox.

Set `REQUIRE_EMAIL_VERIFICATION=true` to test the verification gate. New users may authenticate to the verification screen but cannot access CRM until verification succeeds. Existing users have an unknown verification state after migration and must verify when the gate is enabled; the migration does not invent proof of email ownership.

## Production configuration

Production startup requires `REQUIRE_EMAIL_VERIFICATION=true`, `MAIL_BACKEND=smtp`, `SMTP_HOST`, `SMTP_STARTTLS=true`, a non-example `MAIL_FROM`, secure cookies, encryption and PostgreSQL. Configure `SMTP_PORT`, `SMTP_USERNAME` and `SMTP_PASSWORD` for the chosen service. Inject credentials using Key Vault. The sender domain must have provider-approved SPF/DKIM/DMARC configuration. Configure and verify an actual delivery mailbox before enabling signup. Neither domain ownership nor SMTP deliverability is established by source tests.

Account mail is queued in the transaction that creates its single-use token. Bodies are encrypted in the database and removed after successful delivery. Worker retries reuse the same message ID and token; a crash between SMTP acceptance and SQL commit can produce a duplicate email, but cannot make a token reusable. Provider failures remain failed/retryable jobs rather than successful-looking delivery.

## Security behavior

- Verification links expire after 24 hours; recovery links after 30 minutes; MFA sign-in challenges after five minutes. A replacement link invalidates the preceding token of that purpose. Tokens are random, stored as hashes and consumed atomically.
- Links use fragments, a configured trusted application origin and `Referrer-Policy: no-referrer`. The recovery page removes the fragment from browser history and never automatically authenticates a recovered user.
- Recovery requests return the same message for known and unknown accounts, queue delivery without an SMTP timing dependency and have IP/account limits. Invalid recovery/factor attempts consume their rate allowance even when the business transaction rolls back.
- Password changes and recovery revoke all sessions and pending MFA sign-ins. Recovery does not disable or bypass MFA: an enrolled account must also supply a current authenticator code or unused recovery code.
- TOTP uses the cryptography library's RFC 6238 implementation, 160-bit random secrets, 30-second steps and a one-step clock tolerance. Accepted counters cannot be reused. Secrets and pending enrollment are encrypted. Enrollment expires after ten minutes.
- Ten random 96-bit recovery codes are issued once. Only hashes persist; consumption is atomic and replacement invalidates the prior set. Enabling/disabling MFA revokes other sessions, and account security changes create audit events and queued notices where mail is configured.
- Session listings/revocation name the authenticated user explicitly across their organizations. Device descriptions are untrusted user-agent text. No session token, factor secret, recovery hash or mail body is exposed through the user serializer.

Keep hosts synchronized to a trusted clock. A user who loses their password, mailbox and all second factors requires an operator identity-verification process; there is no security-question bypass or hidden administrator reset endpoint. Define and approve that support process before launch.

## Verification

Run `python -m pytest backend/tests/test_identity.py`. Tests cover verification gating, expiry/reuse, generic recovery responses, session revocation/ownership, password changes, MFA/recovery replay, MFA-preserving resets, failed-reauthentication rate limits and RFC vectors. Browser journeys and live SMTP acceptance are separately recorded in `verification.md`.

References: [OWASP password recovery](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html), [OWASP MFA](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html), [RFC 6238](https://www.rfc-editor.org/rfc/rfc6238).

Organization deletion also requires current-password reauthentication and an unused factor for enrolled accounts; its dedicated attempt limit survives failed transactions. Recovery pages consume new hash links even when the browser is already on the recovery route, then remove the secret fragment.
