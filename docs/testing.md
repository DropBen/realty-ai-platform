# Testing

## Local commands

The root README lists complete verification commands. Backend fixtures create isolated tenant databases, override API/worker sessions, and remove test tables afterward. PostgreSQL tests require a disposable database URL and will destroy its tables. Do not reuse a development database containing work you want to keep.

The suite covers:

- Account creation/login, CSRF/origin rejection, session headers, role restrictions and server validation.
- Cross-tenant direct/list/profile/search/analytics access, composite foreign keys and writes.
- Approval, concurrent review versions, tamper detection, worker reauthorization, idempotent tasks, snooze, expiration, guarded undo and missing provider failures.
- Extraction without authoritative mutation, exact source evidence, conservative parsing and explainable matching.
- OAuth PKCE/state replay, token encryption/refresh, Gmail full/incremental/expired sync, Calendar invalidation, provider timeouts and untrusted output.
- Verified and duplicate Stripe events, canonical state updates, uploads/download isolation, invalid files, scheduling conflicts, database failures, retries/dead letters, export and deletion.

`respx` supplies provider HTTP contracts without contacting or sending to external recipients. Production credentials are not used in these tests.

## Browser journeys

`e2e/workspace.spec.ts` covers desktop/mobile route loading, responsive width, contact creation, preferences/timeline, grounded command results, approval → worker → timeline, explicit unconfigured Google status and new-account isolation. Run with a seeded isolated demo API and worker at `E2E_BASE_URL` (default localhost:8000).

The build host's computer-use runtimes failed to initialize and Chrome could not create Windows IPC pipes. Browser tests are supplied but **local execution/visual inspection is not claimed**. CI runs them on Linux with Chromium and uploads screenshots, traces and logs. Review that output before accepting UI or accessibility quality.

Live Google consent, external sending, calendar mutations, real AI inference, Stripe test checkout, Blob storage and Azure are separate staging certification tests. They are not marked passed by an HTTP mock.
