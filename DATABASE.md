# Database

PostgreSQL 16; SQLAlchemy 2; Alembic via Flask-Migrate. IDs are UUID strings (36-character primary/foreign keys). Timestamps are timezone-aware UTC. Effective dates are separate dates selected by the user. AUD is the only exposed currency; relationships, groups and expenses carry currency columns for future expansion. Do not mix currencies or add conversion without extending every balance/split service and constraint.

| Table | Purpose and important constraints |
|---|---|
| user | Unique normalized phone; unique optional email; hashed password; verification/active flags; session version; theme and avatar |
| person | Contact name/phone/email/notes/photo; owning user; partial unique index permits one self-person per owner |
| relationship | Canonically ordered person pair; unique pair/currency; owner controls local history |
| access | Accepted account/endpoint visibility; unique account per relationship and unique account assignment per endpoint |
| ledger | Signed BIGINT cents; kind; date; actor; source reference; attachment; operation; unique reversal target; optional repayment reference |
| group | Owner; name/description; status; currency; revision |
| member | Group/person membership; optional accepted account; unique group/person and group/account |
| expense | Single payer; amount; method; date; notes; group nullable for standalone bills; attachment; replacement chain; active version |
| share | Expense/person allocation; nonnegative cents; unique participant per expense |
| review | One ledger/expense/group target; acknowledgment/dispute/resolution event; unique resolution reference |
| snapshot | One immutable finalized group snapshot, including net, contributions, shares and transfers |
| transfer | Finalized snapshot debtor/creditor/cents; unique generated ledger reference |
| invitation | Sender, verified target, scoped relationship or membership, expiry, acceptance status |
| attachment | Private randomized stored filename, MIME, length and owner |
| notification | In-app event recipient, message, deep link, read state |
| audit | Append-only actor/action/target/data record |
| operation | Unique actor/key; payload and file fingerprint; committed result |
| reset_token | Only token digest stored; expiry and single-use status |
| rate_bucket | Atomic PostgreSQL fixed-window authentication attempt counters |

All foreign keys use RESTRICT. There is no financial cascade deletion. Financial event tables have both ORM guards and database triggers rejecting UPDATE/DELETE. Expenses may only be superseded by changing active true to false while their group is open; their amounts and shares remain immutable. The database trigger also prevents deleting expense history.

Amounts and group states have CHECK constraints; share sums, endpoint authorization, accepted aliases and cross-record membership are validated by transactional services. Do not expose database credentials to clients or bypass services for financial writes.

`pg_trgm` GIN indexes cover contact names/notes, ledger descriptions, group names/descriptions and expense descriptions. Composite indexes support relationship history and active group expenses. Activity/history pages paginate 40 records with deterministic ordering. Dashboard balances use one grouped aggregate, with batched names/access queries rather than one balance query per row. Group calculation is linear in active shares.

## Migrations

```text
docker compose --profile tools run --rm migrate
```

This executes `flask --app settlebook:create_app db upgrade`. The initial migration is a frozen schema definition, not a runtime `create_all()`. Runtime table creation is not a substitute for migrations. The app database owner needs permission to install `pg_trgm` in its database. For managed databases, have the DBA install it first.

To generate a future revision against a disposable development database:

```text
docker compose exec app flask --app settlebook:create_app db migrate -m "describe change"
docker compose exec app flask --app settlebook:create_app db upgrade
```

Generate revisions in a source-mounted development environment or copy the generated migration back out of the container before rebuilding. Review SQL and constraints manually. Never autogenerate against production. Initial destructive downgrade is intentionally disabled; use the documented backup/restore rollback.
