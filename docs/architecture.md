# Architecture

## Product flow

```mermaid
flowchart LR
  Google[Google Gmail / Calendar] --> Sync[Authorized synchronization]
  Upload[Documents] --> Extract[Bounded extraction]
  Sync --> CRM[(Tenant CRM)]
  CRM --> Context[Scoped retrieval]
  Extract --> Context
  Context --> Analyze[Provider or labelled demo rules]
  Analyze --> Validate[Schema + source validation]
  Validate --> Suggest[Proposed action]
  Realtor[Realtor review] --> Suggest
  Suggest -->|Approved snapshot| Queue[(Durable job)]
  Queue --> Worker[Authorized worker]
  Worker --> CRM
  Worker -->|Specific external permission| Google
  Worker --> Audit[Audit + timeline + usage]
```

## Decisions

**Modular monolith:** FastAPI serves versioned endpoints and the built React assets. Separate routers cover identity, CRM, work and account lifecycle. Services handle actions, intelligence, Google, billing, documents and jobs. This avoids premature service boundaries while separating API and background execution operationally.

**Python + TypeScript:** Pydantic validates inputs and provider output; SQLAlchemy models relational state; React and TypeScript provide a typed interaction layer. PostgreSQL is the production database. SQLite is restricted to development/test workloads. Alembic migrations freeze schema changes. The frontend uses TanStack Query for server state and an explicit API client; it does not persist customer records in browser storage.

**Frontend builds:** esbuild produces hashed ES modules, lazy route chunks and CSS; Vite is the optional hot-reload development server. A direct synchronous CLI build works in Windows environments that prohibit persistent child-process IPC. Source code is shared; there is no separate mock frontend.

**Queue in the database:** Jobs and approved actions commit together. Workers atomically claim due records, retry bounded failures, and retain dead jobs. One worker is the deployment default. External side effects cannot be made transactionally atomic with SQL; their execution claim is committed before the network call and ambiguous outcomes require reconciliation.

**Authorization:** Sessions resolve user membership on every request. Tenant-scoped ORM criteria, write guards, composite foreign keys and central RBAC defend organization boundaries. Identity discovery, Stripe customer mapping and worker scheduling are explicit privileged exceptions. Raw SQL is not available to natural-language queries. Database RLS is not enabled; see security documentation for the remaining defense-in-depth work.

**Evidence over inference:** Confirmed preferences and unverified extraction are distinct records. Matching uses only recorded preferences and reports unknown/conflicting criteria. AI summaries stay labelled analysis. An approval records the exact payload and actor; editing requires another review.

**Operational boundaries:** API and worker share an image and database. Azure Blob stores documents in production. Provider APIs are reached only at hardcoded official service origins. Google account ownership is checked before Calendar mutations. Teams share CRM visibility within an organization; this is not a per-agent private inbox product.
