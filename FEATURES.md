# Requirement compliance

“Implemented” below means a source implementation and relevant UI/service path exist. It does **not** mean database or browser end-to-end verification passed. Infrastructure-dependent verification remains blocked as detailed in `docs/VERIFICATION.md`.

| Specification area | Implementation | Verification status |
|---|---|---|
| Original minimal stack | Flask/PostgreSQL/SQLAlchemy/Jinja/HTMX/Alpine, compiled Tailwind, Gunicorn/Nginx/Compose | Imports, assets, migrations SQL checked; deployment blocked |
| Visual identity | Prototype CSS/tokens, purple gradient, dark/light themes, mobile shell, fixed bottom nav, safe-area, reduced-motion | 16 rendered templates; both-theme screenshots; physical device checks pending |
| Accounts | Registration, E.164 phone, unique optional email, secure password, sessions, profile/photo, reset/change, deactivation | Public forms/CSRF checked; PostgreSQL account tests blocked; SMTP delivery pending |
| Contacts/sharing | Private contacts with optional phone/email/photo/notes; automatic phone-based invitations for unverified accounts, explicit acceptance, queued invitations for later registration | Multi-user integration and alias-reuse tests supplied, blocked |
| Individual ledger | Money given/taken, repayments, splits/groups, adjustments/reversals, receipts, effective date, actor/source/reference metadata | Pure arithmetic checked; persistence/authorization tests blocked |
| Immutable history | ORM guards, PostgreSQL triggers, reversal source refs, audit | DDL generated; trigger test blocked |
| Reviews/disputes | Acknowledge/dispute/resolve, notes, history, finalization blocking | PostgreSQL tests supplied, blocked |
| Repayments | Partial/full, direction/overpayment protection, optional entry reference and receipt, third-party local perspective | Integration/concurrency tests supplied, blocked |
| Split bills | Equal/custom, subsets, any payer, deterministic cents, all pair obligations, atomic posting, attachment/date/notes | Pure allocation checked; third-party/shared tests blocked |
| Groups | Open/review/finalized/archived, members/invitations, different payers, isolated expenses, contributions/shares/net, deterministic preview | Pure net/settlement checked; lifecycle tests blocked |
| Finalization | Explicit revision-confirmation, dispute/membership/share checks, immutable snapshot, all pairs, atomic/idempotent freeze and notifications | Integration/concurrency tests supplied, blocked |
| Corrections | Versioned open-group expenses; linked reversal/adjustment after finalization | Source review complete; PostgreSQL tests blocked |
| Dashboard/people/activity | Correct personal-only totals, counterpart perspective, third-party ledgers labeled separately, filters, paginated histories | Templates rendered; live query behavior blocked |
| Search | Authorized PostgreSQL queries and trigram indexes across contacts, ledger, groups and expenses/bills | SQL compiled; live/performance checks pending |
| Attachments | Private filesystem volume, type/size validation, image optimization, owner/shared-scope checks, authenticated download | Source/fixture review; PostgreSQL upload/IDOR tests blocked |
| Notifications/sync | In-app unread state, scoped event messages, committed-snapshot polling token and refresh prompt | Source review; live two-device behavior pending |
| PWA | Manifest/icons, standalone, install capability over HTTPS/localhost, offline non-sensitive shell, offline submit guard | Manifest/assets and cache policy checked; physical install and offline browser workflow pending |
| Deployment/docs | Docker Compose, migration service, persistent volumes, health checks, VPS HTTPS/backup/restore/upgrade guidance | Config source supplied; Docker execution blocked |
| Quality gates | Unit/static/property, PostgreSQL integration/concurrency, Playwright workflows, three audit passes | See exact results; no production-readiness assertion |

## Deliberate optional exclusions

Browser push and multi-payer allocation within one bill are optional in the original specification and are not included. Offline financial mutation is deliberately disabled, as expressly permitted; it never reports false persistence. Local contact creation does not automatically expose any records. There is no external payment processing: all payment actions record events that users report.

## Implementation limits

Groups and individual splits support up to 200 members/participants per operation. Financial amounts are capped at AUD 1 billion per entry. Activity and person history paginate 40 rows. Group list and invitation/notification lists currently display the latest 100 records; older groups remain discoverable by search and known links. These list limits should be revisited as usage grows. Existing independent user-entered histories are not automatically reconciled when sharing is accepted; the system never guesses that two historical records represent the same real-world payment.

Design additions required for real security, disputes and financial operations use the supplied styles, but no pixel-perfect equivalence claim is made. SMTP/TLS configuration, zero-skip PostgreSQL tests, actual device installation and load measurements remain release gates, not removed features.
