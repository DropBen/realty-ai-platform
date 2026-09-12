# Security and trust boundaries

## Implemented controls

- Salted scrypt password hashes; random session tokens stored only as hashes. Session cookies are HttpOnly, SameSite=Lax and secure in production. Session membership is rechecked on each request and again before a worker executes an approval.
- Exact-origin checks plus session-bound CSRF tokens for mutations. Login/registration require JSON and have database-backed rate buckets. Edge rate limiting remains necessary for public deployment.
- Central roles: owner (all), admin (administration/billing except organization deletion), agent (CRM/review/external actions), assistant (read/write drafts), viewer (read). Owner elevation is not exposed through the team API.
- ORM query scoping and write guards by organization. Composite foreign keys prevent a record in one tenant from linking a contact/property/deal in another. Tenant isolation tests cover direct IDs, lists/counts, profile context, natural-language search, foreign keys, documents, writes and analytics.
- Input allowlists/Pydantic validation, parameterized SQL, React text escaping, CSP, anti-framing, nosniff and no-store headers. No arbitrary SQL, URLs or execution tools are exposed to the model.
- OAuth PKCE, one-use state bound to the active session, ten-minute expiry, encrypted tokens, bounded requests and token revocation. Scope escalation is explicit. External Calendar changes require the connected owner.
- Stripe signature verification on raw bytes, timestamp tolerance, idempotent event insertion and canonical subscription lookup. Client-provided plan state never grants access.
- Upload type/size checks; PDF extraction runs in the worker; downloads are authenticated attachments. Scanned files remain OCR-required. Local file paths are resolved under the storage root. Blob keys include tenant IDs.
- Structured logs omit request bodies, query strings, OAuth codes, tokens and passwords. Audit rows contain actors, actions, targets and safe metadata. Provider errors expose stable codes, not raw bodies or stack traces.

## AI safety

Email/document content is untrusted data. Prompt instructions explain that boundary, but prompts are not the security mechanism. There are no model execution tools, retrieval is tenant-scoped, output is schema-validated, cited IDs are allowlisted, extracted quotes must occur in the source, and consequential changes remain proposals. Approvals snapshot exact payloads and require current permissions. This reduces prompt-injection impact; it does not claim to make model summaries factually infallible.

Never infer protected characteristics or rank housing opportunities using them. Matching evaluates declared budget/location/property preferences only and explains its factors. Client communication still needs professional review.

## Before a production launch

This repository has not passed a penetration test, independent AI red team, load test, accessibility audit or customer-data review. Configure identity verification, password recovery/MFA or an enterprise identity provider before broad public signup. Enforce ingress body/connection limits and abuse protection. Add hardened PDF scanning/OCR infrastructure and resource isolation for hostile documents. Restrict private network and storage access, grant least-privilege database/service identities, and test backups/restoration.

PostgreSQL RLS is not enabled. Application scoping is tested, but privileged SQL and any new query path require review. PostgreSQL [row-security policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) are a potential additional isolation layer; introducing them requires separate non-owner runtime roles and scoped transaction configuration, not merely enabling a flag.

## Data lifecycle

Google disconnect revokes tokens, clears connection secrets and cursors, and retains imported CRM history. It does not silently delete business records. Owners may export data and explicitly delete an organization after all Google connections are disconnected and Stripe billing is canceled. Deletion removes tenant rows and documents; user identity is removed only when it has no other memberships. Audit history is part of the tenant deletion. Backups follow the operator's separately configured retention policy.

Bulk exports are bounded at 20,000 rows per table. Large-tenant export, retention scheduling and deletion of failed orphan uploads require operational procedures. A failed cross-system deletion can require reconciliation; object storage and SQL do not share a transaction.
