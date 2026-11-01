# Development

## Local Python

Create a Python 3.12+ virtual environment and install `requirements.lock`. Configure DATABASE_URL for a disposable PostgreSQL database, SECRET_KEY, COOKIE_SECURE=false and UPLOAD_FOLDER. Run:

```text
flask --app settlebook:create_app db upgrade
flask --app settlebook:create_app run --port 8000
```

Use the interpreter in your activated virtual environment. For Windows, activation is `.\.venv\Scripts\Activate.ps1`; Ubuntu is `source .venv/bin/activate`. Debug mode is local-only. The server fails startup without a sufficiently long secret and rejects SQLite URLs.

## Frontend

```text
npm ci
npm run css
```

Tailwind utilities compile into local `static/tailwind.css`. Prototype-derived `design.css` supplies the visual design. Vendored JS is in `static/vendor/`; after intentional package updates copy `node_modules/htmx.org/dist/htmx.min.js` and `node_modules/alpinejs/dist/cdn.min.js` into that directory and rerun browser tests. Preserve upstream license notices in `docs/vendor-licenses/`. No CDN is required at runtime.

## Adding a feature

1. Define authorization and financial invariants first. Decide whether the data is a private contact, shared relationship, or isolated group record.
2. Extend models and create a reviewed migration. Preserve RESTRICT relationships and immutable history. Add indexes for expected reads.
3. Put financial behavior in services, with row locks, operation keys, source references, audit and recipient notifications in the same transaction. Never derive money using binary floats.
4. Add a thin route validating input. Use authenticated and CSRF-protected forms/JSON. Reuse Jinja macros and existing CSS variables for both themes.
5. Test the successful path, unauthorized user, retry, failure rollback and relevant races. Run real PostgreSQL integration tests.
6. Update route/schema/feature documentation and visual snapshots. Do not equate a rendered fixture with end-to-end success.

## JSON mutation contract

`POST /action/<action>` accepts a JSON object and `Idempotency-Key` plus session cookie and `X-CSRFToken`. Actions: entry, reverse, expense, group, member, group-status, finalize, invite, accept, review. The matching HTML forms show the exact fields. Monetary API fields are decimal strings. Participants are person-ID lists; custom `shares` map person ID to decimal string. Source amounts/currency are validated server-side. Successful JSON returns `{id?, path}`; errors return `{error}` with 400/403/404/409/429/500.

Retrieve a CSRF token from a rendered page's meta tag when using the future API internally. Never disable CSRF just to make an integration easier. The tests disable it only in their dedicated fixture; a separate test verifies rejection when enabled.

## Troubleshooting

- Connection refused: PostgreSQL isn't reachable; use Compose health checks and the configured database URL. Do not switch to SQLite.
- 409: duplicate phone/email, conflicting operation key, stale review revision, already-linked endpoint, or frozen group. Refresh and inspect the returned message; do not blindly generate new keys after uncertain persistence.
- Login loops on localhost: COOKIE_SECURE=true over HTTP. Use false locally, true on HTTPS deployments.
- Reset unavailable: configure SMTP and PUBLIC_URL. Do not log or display reset tokens as a workaround.
- Missing styles: rebuild Tailwind, verify vendored files, and restart/rebuild the container with updated source.
- Missing uploads after deployment: verify the persistent attachments volume and app UID 10001 permissions.
- Group finalization blocked: inspect unresolved disputes, status and revision. Only the disputing user resolves their dispute.
- Optional note/description text is escaped; HTML markup isn't accepted.

Run `ruff check .`, `pytest -v`, and `npm run test:ui` after relevant changes. CI runs Ruff and the full PostgreSQL Python suite; browser tests require the separate running app and are provided as a local release gate.
