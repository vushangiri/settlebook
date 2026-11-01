# Settlebook

A mobile-first Flask application for personal IOUs, repayments, split bills, and isolated group ledgers. PostgreSQL is the only supported database. The supplied prototype is retained in `reference/approved.html`; production templates use its visual tokens and layout.

**Verification status:** implementation is delivered for local verification, not certified production-ready. Read `TESTING.md` and `docs/VERIFICATION.md` before entering real financial data. PostgreSQL/Docker execution was unavailable in the authoring workspace. No SQLite substitution, fake persistence, or demo data is used by the application.

## Start on Windows (Docker Desktop, Linux containers)

Extract the ZIP, open PowerShell in the directory containing `compose.yaml`, and run:

```powershell
Copy-Item .env.example .env
# Edit .env: set independent long random hex POSTGRES_PASSWORD and SECRET_KEY.
notepad .env
docker compose up -d db
docker compose build
docker compose --profile tools run --rm migrate
docker compose up -d app nginx
Start-Process http://localhost:8080
```

Use hex secrets (letters a–f and digits) to avoid database URL escaping problems. The sample `.env` values are placeholders, not deployable credentials. `COOKIE_SECURE=false` is for localhost HTTP only. If Docker cannot resolve or pull images, fix Docker Desktop's networking before continuing.

## Start on Ubuntu

With Docker Engine and the Compose plugin installed:

```bash
cp .env.example .env
# Generate two independent values and paste them into .env:
openssl rand -hex 32
openssl rand -hex 32
nano .env
chmod 600 .env
docker compose up -d db
docker compose build
docker compose --profile tools run --rm migrate
docker compose up -d app nginx
```

The app listens only on `127.0.0.1:8080`. Use an SSH tunnel for private remote testing or configure HTTPS as described in `DEPLOYMENT.md`. Register your own account; there are no seeded users or default passwords.

## Required verification before use

These commands work in PowerShell and Bash:

```text
docker compose --profile test run --rm tests
docker compose --profile test run --rm tests pytest -v -m concurrency
docker compose --profile test run --rm tests ruff check .
```

Tests use a separate disposable PostgreSQL container and run actual Alembic migrations. They never use the application database. For browser tests, install Node.js, then, with the app running:

```text
npm ci
npx playwright install chromium
npm run test:ui
```

Run browser tests only against a disposable development app; they create test accounts and financial records. On Ubuntu, use `npx playwright install --with-deps chromium` when browser system libraries are missing. Detailed commands, expected outcomes, and cleanup appear in `TESTING.md`.

## Contents

- `settlebook/`: application factory, database models, accounting functions, business services, routes, templates and compiled local assets.
- `migrations/`: frozen Alembic schema, PostgreSQL immutability triggers and search indexes.
- `tests/`: pure arithmetic, static, PostgreSQL integration/concurrency and Playwright tests.
- `deploy/`, `compose*.yaml`, `Dockerfile`: VPS/local deployment.
- `docs/screenshots/`: synthetic-data Jinja template screenshots, both themes. They are visual evidence, not proof of database operation.
- `tools/render_fixtures.py`: offline template-rendering QA helper, never used by production.
- `ARCHITECTURE.md`, `DATABASE.md`, `FINANCIAL_RULES.md`, `FEATURES.md`, `SECURITY.md`, `TESTING.md`, `DEPLOYMENT.md`, `DEVELOPMENT.md`: implementation and operations documentation.

Optional SMTP configuration enables email password recovery. Phone ownership verification is administered using the CLI and must be backed by independent evidence. Neither feature silently pretends to be configured.
# settlebook
