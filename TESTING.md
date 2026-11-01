# Testing

The exact authoring results and remaining release gates are in `docs/VERIFICATION.md`. Tests never substitute SQLite for PostgreSQL.

## Windows PowerShell / Ubuntu Docker

From the project root, after configuring `.env`:

```text
docker compose --profile test run --rm tests
docker compose --profile test run --rm tests pytest -v -m postgres
docker compose --profile test run --rm tests pytest -v -m concurrency
docker compose --profile test run --rm tests ruff check .
```

`test-db` is a separate temporary PostgreSQL 16 container. `pgapp` recreates its public schema and applies the actual Alembic migration for each integration test. Do not change TEST_DATABASE_URL to point to any valuable database. The fixture additionally requires `test` in the database name. Tests are sequential; do not use pytest-xdist against the same database.

Expected: all tests pass with **zero infrastructure skips** in Docker. There are 19 PostgreSQL test functions, including four threaded concurrency tests. Pure property tests include 100 deterministic randomized cases.

If only pure tests are wanted:

```text
docker compose --profile test run --rm tests pytest -v -m "not postgres"
```

On an already installed Python 3.12+ environment:

```text
python -m venv .venv
```

PowerShell:

```powershell
.\.venv\Scripts\python -m pip install -r requirements.lock
.\.venv\Scripts\python -m pytest -v -m "not postgres"
$env:TEST_DATABASE_URL="postgresql+psycopg://test:YOUR_PASSWORD@localhost:5432/settlebook_test"
.\.venv\Scripts\python -m pytest -v -m postgres
```

Ubuntu:

```bash
.venv/bin/pip install -r requirements.lock
.venv/bin/python -m pytest -v -m 'not postgres'
TEST_DATABASE_URL='postgresql+psycopg://test:YOUR_PASSWORD@localhost:5432/settlebook_test' .venv/bin/python -m pytest -v -m postgres
```

The Compose application DB is deliberately not published on the host. Prefer the Docker test commands rather than opening database ports.

## Browser tests

Start a disposable local development app using README commands, then:

```text
npm ci
npx playwright install chromium
npm run test:ui
```

For a different target, PowerShell: `$env:BASE_URL="http://localhost:8080"`; Bash: `BASE_URL=http://localhost:8080 npm run test:ui`.

The three Playwright scenarios cover mobile registration/navigation; entry and partial repayment; dark persistence; search; equal split rounding; group isolation, review and finalization; browser validation; manifest and safe offline fallback. They create synthetic accounts and records. Runtime screenshots go into `docs/runtime-screenshots/`, traces into `test-results/`, and the HTML report into `playwright-report/`. Do not run against production.

To check the full screenshot set visually, compare `docs/screenshots/` against `reference/approved.html`. Existing screenshots were captured from real Jinja output populated with synthetic fixtures; they do not demonstrate live backend success.

## Financial and security test coverage

- Strict cents parsing and bounds, rounding conservation, custom-share validation, 100 randomized net/settlement cases.
- Real migration, registration/login/logout, session invalidation, sharing consent, opposite perspectives, unauthorized reads/writes/search/attachments.
- Partial/full repayments, immutable database trigger, exact-once posting, changed-key payload rejection, reversal history, third-party splits/repayments, shared alias reuse.
- Open-group isolation, corrections, dispute resolution, stale preview rejection, finalization retry/freeze.
- Notifications/sync token, receipt processing, single-use/expired reset tokens, rate limits, injected rollback after ledger flush.
- Concurrent duplicate posting, concurrent overpayment prevention, concurrent group finalization.

## Release gates

Run the entire suite on PostgreSQL with no skips, run Playwright, exercise migrations on a restored backup, validate HTTPS/PWA installation on actual Android and iOS devices, test SMTP delivery using a development mailbox, and benchmark realistic ledger/group sizes. Passing pure tests does not substitute for these checks.
