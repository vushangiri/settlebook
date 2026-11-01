# Architecture and implementation decisions

A Flask modular monolith serves Jinja HTML, HTMX search fragments, local Alpine interactions, and authenticated JSON mutations through the same services. PostgreSQL owns all financial state. Gunicorn serves the app behind Nginx. Attachments live in a persistent, private Docker volume. No worker queue, external search engine, or second database is required.

## Module boundaries

| Module | Responsibility |
|---|---|
| `accounting.py` | Parse decimal strings to cents, split shares, net group positions, deterministic settlement; no database or HTTP dependencies |
| `models.py` | Normalized records, foreign keys, monetary/identity constraints, ORM immutability |
| `services.py` | Authorization, accepted identity aliases, posting, sharing, group state transitions, review resolution, notifications and audit |
| `routes.py` | Session auth, CSRF-compatible forms/JSON, validation, upload processing, filters, presentation queries |
| `__init__.py` | Configuration, extensions, headers, session validation, administrative/maintenance CLI |
| `templates/` | Server-rendered functional screens, shared macros, original visual design |
| `static/` | Compiled Tailwind, prototype CSS, vendored HTMX/Alpine, online status, polling and PWA shell |

## Transaction boundary and locks

Every financial `/action/<name>` request locks its actor with PostgreSQL `FOR NO KEY UPDATE`, obtains a unique actor/idempotency-key row, checks the request hash, runs the service, records the result, and commits exactly once. Notifications/audit records are in that transaction. The actor lock permits foreign-key key-share locks. Relationship/group row locks serialize balance-dependent operations and group freeze transitions. Group transfers are sorted by canonical person pair. Deadlocks or connection failures produce no success response; the client may retry the same key. Idempotency keys are not expired by a cleanup job.

A committed response lost to the network is safe to retry: the stored operation result is returned. Reusing a key with a different payload or attachment hash returns 409. A failed transaction rolls back all posted rows. Orphan files from a rolled-back upload are removed by the maintenance command after 24 hours.

## Identity and visibility

An account has one self-person and private contact-person records. A relationship is one canonical ordered pair of people. An accepted invitation grants access to one endpoint of one relationship, or one group membership. Matching phone text grants nothing. Only a verified target account can accept. One relationship endpoint cannot be assigned to two accounts.

Accepted sharing provides identity aliases for later posting: an authorized existing shared relationship is reused when another user's local self/contact representation denotes the same accepted accounts. Linking never copies historical ledger rows. Independently created histories are not guessed to be duplicates or silently deleted; reconcile actual duplicate user-entered transactions through reversals. A phone match alone never merges financial histories.

Group owners administer local members. Accepted registered members can view/review expenses and add expenses while open. Finalization gives accepted members access to their resulting personal obligations; it does not expose unrelated third-party ledgers.

## Synchronization

The browser polls `/api/sync` every 12 seconds while visible and online. The server hashes the current committed ordered notification IDs and read states. A change shows an explicit refresh banner, avoiding overwriting a form in progress. This is a snapshot change token, not a sequence cursor: late commits cannot be skipped because of sequence allocation order. Reloading reads balances from authoritative ledger rows. Reconnection polls again. No financial data is cached by the service worker.

## Initial ambiguities resolved

- Single payer per expense, as required by the bill definition; the workflow's “multiple payers where supported” does not require a multi-payer bill. Groups support different payers across expenses.
- Repayments cannot exceed the current debt or cross zero. Record a separate money-given/taken event for an advance.
- Only the person who raised a dispute can resolve it; administrators can correct an expense after resolution. Unresolved disputes block finalization.
- Reopening review increments its revision. Finalization requires an explicit confirmation and the exact reviewed revision.
- Finalized groups remain frozen. Subsequent financial corrections are linked ledger reversals or explicit adjustments, never a rewritten settlement snapshot.
- Optional email enables recovery; without an email, self-service email reset is unavailable.
