# Google integration

Calendar writes now require the reviewed imported ETag and use If-Match. A changed or unversioned event requires synchronization and a new review; active duplicate syncs share a database reservation. See [review/failure boundaries](review-failure-audit.md).

Create a Google Cloud OAuth web application, enable Gmail and Calendar APIs, configure the consent screen, add test users and register the exact callback URL from `GOOGLE_REDIRECT_URI`. Supply the client ID, secret and encryption key to the server, set `DEMO_MODE=false`, and use a separate non-demo database. The connection UI never says connected merely because it was clicked.

The initial request asks for OpenID/email identity, Gmail readonly and Calendar readonly. Gmail send and Calendar event modification are separate explicit capability requests. State is session-bound, short-lived and single-use; PKCE binds the exchange. Offline refresh tokens are Fernet-encrypted, rotated from refresh responses and revoked on disconnect.

## Gmail

Initial synchronization imports up to 90 days, excluding promotions/social categories, and retains business-relevant mail or messages from existing CRM contacts. It snapshots the history cursor before importing so subsequent sync catches concurrent mail. Incremental sync uses history additions and deduplicates by organization, mailbox owner and provider message ID. An expired history cursor triggers a fresh bounded import, following [Google's Gmail synchronization contract](https://developers.google.com/workspace/gmail/api/guides/sync).

Message threads, plain text/snippets, participants, direction, timestamps and attachment metadata are stored. Raw email HTML is never rendered. New relevant contacts and analysis/workflow jobs are created. Mailbox deletions do not erase retained CRM history. Attachments are metadata only; their bytes are not automatically downloaded. Email relevance is a conservative keyword/contact rule, not a classifier trained for every brokerage.

Approved email actions create MIME plain-text messages with a deterministic Message-ID and call Gmail send once. Timeouts/5xx are ambiguous and require reconciliation. There is no automatic resend guarantee and no claim of exactly-once delivery across Google's API and SQL.

## Calendar

Discovery lists calendars; the default sync targets primary. The service accepts a calendar ID for future selection UI. Sync handles pagination, nextSyncToken, canceled events and 410 invalidation according to [Google's Calendar sync contract](https://developers.google.com/workspace/calendar/api/guides/sync). Events are owned by their connected account. Mutations pass through the approval action registry and conflict checks.

Available-time recommendations consider recorded calendar intervals, appointment duration and organization office hours. Travel-time routing, time-zone interpretation for all-day provider events, complex recurrence editing and showing-sequence optimization are not certified features. Refresh Google before relying on availability; unsynced calendars can conflict.

## Validation and rollout

HTTP contract tests cover OAuth state/replay, encryption, token refresh, full/incremental Gmail sync, cursor expiry, Calendar reset and ambiguous external calls. They do not replace a live OAuth consent test. Production access may require Google app verification and any review required for the selected scopes. Configure exact redirect URIs in each environment and never share demo and production tokens.

## Timezones and synchronization safety

Date-only all-day events use the calendar timezone, preserving 23/25-hour daylight-saving days. Explicit offsets disambiguate repeated times; nonexistent or ambiguous naive timestamps are rejected. Recurrence instance identity and original start metadata are retained, but recurrence-series editing and travel routing remain future scope. Local and approved external appointment writes serialize their conflict check within the workspace; Google can still change independently after synchronization. Imports checkpoint without advancing final cursors until completion; deduplication makes a resumed read safe. Failed connection/sync work is surfaced through job error codes and Settings. Live provider staging acceptance remains required.

## Authority and failure recovery

OAuth state is bound to both the login session and originating workspace. Callback processing checks external permission and, after the provider round trip, rechecks the current session/workspace and membership before storing credentials. Token and identity responses are typed and validated. API calendar reads and worker imports require external permission.

A revoked refresh grant, absent refresh token or provider 401 marks the matching connection `reconnect_required`, records a stable error and stops automatic job retries. Failure persistence compares the failed credential fingerprint so an old request cannot disable a freshly reconnected account. Reconnect through Settings; disconnect remains available. A mailbox identity cannot currently be replaced with a different account for the same user/workspace: reconnect the original mailbox. Retained import identifiers belong to that mailbox.

A successful email response must contain a resource ID; calendar create/update must confirm the expected ID. Malformed or incomplete success responses leave the action uncertain, with no fabricated sent record and no automatic resend. Verify Google directly before creating another action. The full ingest/evidence/review/send/timeline test replaces only provider HTTP; it is not live delivery evidence.
