# Verification and audit report

Date: 1 November 2026. Status: source implementation delivered; infrastructure-dependent release gates remain open. Do not describe this package as production-ready.

## Executed successfully

| Check | Result | Evidence |
|---|---|---|
| Python test suite | 126 passed; 19 skipped | `pytest-results.txt`, `pytest-results.xml` |
| Randomized accounting | 100 seeded cases included in the passing total | `tests/test_accounting.py` |
| Ruff | All checks passed | `lint-results.txt` |
| PostgreSQL DDL compilation | All model table definitions compile | `tests/test_static.py` |
| Alembic offline upgrade | Full PostgreSQL migration SQL emitted | `migration.sql` |
| Jinja | All templates compile; 16 main screens render with synthetic fixtures | Static tests and `tools/render_fixtures.py` |
| Frontend | npm dependency install and Tailwind build completed; local JS assets included | package lock and static assets |
| Playwright discovery | All 3 end-to-end scenarios discovered | `tests/ui/workflows.spec.js`; discovery is not execution |
| Browser visual checks | 16 screen fixtures inspected; no horizontal overflow observed in the 410px application shell; theme toggle/reload and custom-share reveal checked | 32 JPEG screenshots and `visual-results.json` |
| Pure calculation benchmark | 1,000 expenses × 200 participants (200,000 share rows) in approximately 0.049 seconds in this workspace | `accounting-benchmark.json`; excludes DB/network/HTML |

The passing count includes parameterized/property cases, not 126 independent end-to-end features. Screenshots contain synthetic example records, render actual production templates, and disable CSS animations only in the QA fixture wrapper for stable captures. They do not establish successful persistence, authentication or settlement execution. App width was inspected in a desktop browser's mobile-sized shell; actual narrow-device viewports and software keyboards still need Playwright/device verification.

## Blocked, not passed

- 19 PostgreSQL tests: real schema application, persistence, permissions, sharing/alias reuse, group isolation/corrections/disputes/finalization, rollback, trigger enforcement, uploads, notifications, password recovery, rate limiting and four concurrency scenarios.
- Docker build, Compose boot/health checks, persistent-volume restart, production migration and backup/restore drills.
- All 3 Playwright end-to-end scenarios against a running PostgreSQL-backed application. Only test discovery and separate cloud-browser fixture checks ran.
- Real SMTP delivery, HTTPS issuance/renewal, Android/iOS installation, two real devices synchronizing, and PostgreSQL query/load benchmarks.

PostgreSQL and Docker binaries were absent. A system package installation attempt failed with workspace setgroups/setegid permission errors. Python/npm dependencies were available. No SQLite substitute was introduced. Executing offline migration generation is not equivalent to applying the migration to PostgreSQL.

## Audit 1 — Functional coverage

Reviewed the original specification against service actions, routes, templates, schema and documentation. Added explicit third-party repayment/adjustment controls, optional repayment references, group paid/share totals, sharing sender identity, profile image handling and all required financial state transitions. Added a detailed feature matrix in `FEATURES.md` and generated `ROUTES.md`.

Open checks: actual end-to-end runtime behavior; full original-interaction equivalence; real PWA installation. Optional browser push and multi-payer-in-one-bill functionality are excluded as permitted by the original specification. No required financial workflow is intentionally replaced with a demo handler.

## Audit 2 — Financial and security integrity

Reviewed cents-only arithmetic, opposing perspectives, third-party payer attribution, sharing consent, alias reuse, open-group isolation, all-pair finalization, review locks/revisions, compensating corrections, immutable triggers, transaction rollback and idempotency fingerprints. Added endpoint-assignment uniqueness; file-content hashes in idempotency; actor session revalidation after locking; atomic registration/photo persistence; pixel-count upload rejection; same-ledger repayment references; and a cross-user repayment race test.

Open checks: all database integration/concurrency tests. Source inspection cannot certify race safety or prove that no high-severity defects remain. The package must not be used for authoritative records until these tests pass in the intended runtime.

## Audit 3 — UI, performance and deployment

Reused supplied design variables and layout CSS; retained dark/light contrast, gradient balance card, safe areas, bottom navigation and reduced-motion behavior. Fixed quick-action styling after screenshot inspection. Captured all 16 main templates in both themes. Added actual PostgreSQL deployment, migration service, private volumes, non-root app, CI, exact Windows/Ubuntu commands, recovery documentation and a measurable pure-accounting benchmark.

Open checks: live database performance; narrow device viewport and keyboard behavior; full UI workflows; real deployment/backup/TLS/PWA. The existing screenshots are template visual QA evidence, not deployed-site evidence.

## Run the remaining gates

From the extracted directory, follow README setup, then:

```text
docker compose --profile test run --rm tests
docker compose --profile test run --rm tests pytest -v -m concurrency
npm ci
npx playwright install chromium
npm run test:ui
```

Expected PostgreSQL run: no infrastructure skips. A failed test is a defect to investigate, not permission to bypass the check. `TESTING.md` provides PowerShell and Ubuntu alternatives and explains disposable test data.
