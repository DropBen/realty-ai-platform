# Security and trust boundaries

## Implemented controls

- Salted scrypt password hashes; random session tokens stored only as hashes. Session cookies are HttpOnly, SameSite=Lax and secure in production. Session membership is rechecked on each request and again before a worker executes an approval.
- Exact-origin checks plus session-bound CSRF tokens for mutations. Login/registration require JSON and have database-backed rate buckets. Edge rate limiting remains necessary for public deployment.
- Central roles: owner (all), admin (administration/billing except organization deletion), agent (CRM/review/external actions), assistant (read/write drafts), viewer (read). Owner elevation is not exposed through the team API.
- ORM query scoping and write guards by organization. Composite foreign keys prevent a record in one tenant from linking a contact/property/deal in another. Tenant isolation tests cover direct IDs, lists/counts, profile context, natural-language search, foreign keys, documents, writes and analytics.
- Input allowlists/Pydantic validation, parameterized SQL, React text escaping, CSP, anti-framing, nosniff and no-store headers. No arbitrary SQL, URLs or execution tools are exposed to the model.
- OAuth PKCE, one-use state bound to the active session, ten-minute expiry, encrypted tokens, bounded requests and token revocation. Scope escalation is explicit. External Calendar changes require the connected owner.
- Stripe signature verification on raw bytes, timestamp tolerance, idempotent event insertion and canonical subscription lookup. Client-provided plan state never grants access.
- Upload type/size checks; PDF extraction runs in a separate process with a 30-second deadline and Linux 20-second CPU/512-MB address-space limits; downloads are authenticated attachments. Scanned files remain OCR-required. Local file paths are resolved under the storage root. Blob keys include tenant IDs.
- Structured logs omit request bodies, query strings, OAuth codes, tokens and passwords. Audit rows contain actors, actions, targets and safe metadata. Provider errors expose stable codes, not raw bodies or stack traces.

## AI safety

Email/document content is untrusted data. Prompt instructions explain that boundary, but prompts are not the security mechanism. There are no model execution tools, retrieval is tenant-scoped, output is schema-validated, cited IDs are allowlisted, extracted quotes must occur in the source, and consequential changes remain proposals. Approvals snapshot exact payloads and require current permissions. This reduces prompt-injection impact; it does not claim to make model summaries factually infallible.

Never infer protected characteristics or rank housing opportunities using them. Matching evaluates declared budget/location/property preferences only and explains its factors. Client communication still needs professional review.

## Before a production launch

This repository has not passed an independent penetration test, live model red team, full accessibility audit or customer-data review. Email verification/recovery, optional MFA, automated axe/keyboard checks, offline adversarial AI cases and a short isolated load baseline are implemented; see verification.md for executed results. Enforce ingress body/connection limits and abuse protection. PDF process limits reduce parser resource risk but are not a malware scanner or an operating-system sandbox. Add antivirus/scanning infrastructure according to the approved document threat model. Restrict private network and storage access, grant least-privilege database/service identities, and test backups/restoration.

PostgreSQL RLS is not enabled. Application scoping is tested, but privileged SQL and any new query path require review. PostgreSQL [row-security policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) are a potential additional isolation layer; introducing them requires separate non-owner runtime roles and scoped transaction configuration, not merely enabling a flag.

## Data lifecycle

Google disconnect revokes tokens, clears connection secrets and cursors, and retains imported CRM history. It does not silently delete business records. Owners may export data and explicitly delete an organization after all Google connections are disconnected and Stripe billing is canceled. Deletion removes tenant rows and documents; user identity is removed only when it has no other memberships. Audit history is part of the tenant deletion. Backups follow the operator's separately configured retention policy.

Bulk exports are bounded at 20,000 rows per table. Large-tenant export, approved business retention and crash-orphan inventory require operational procedures. Normal rollback cleans new uploads; committed deletion uses a persistent retry queue. Power loss between blob upload and SQL commit can still require reconciliation; object storage and SQL do not share a transaction.

Account-specific controls and MFA policy are in [account security](account-security.md). Organization deletion reauthenticates with password and a current factor when MFA is enrolled. Actual streamed request bodies are bounded before mutation, including chunked input; rate-limit responses include Retry-After. Offline source validation also verifies extracted amounts against quoted numbers, rather than accepting any nearby quote.
