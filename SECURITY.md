# Security model

## Implemented controls

- Werkzeug password hashing; minimum 12-character passwords; session version invalidates old sessions after password reset/change, phone change or deactivation.
- Flask-WTF CSRF on POST, including JSON `X-CSRFToken`; SameSite=Lax and HttpOnly cookies; Secure in production; seven-day session maximum.
- Atomic PostgreSQL authentication/reset rate buckets. The trusted proxy setting is enabled only in the supplied internal Nginx topology; Nginx overwrites forwarded IP headers. Do not expose the app's port or enable proxy trust behind arbitrary clients.
- Explicit relationship/group authorization on reads, writes, attachments, search, sharing, and review targets. Knowing a UUID or a phone number grants no financial access.
- Independent phone verification plus scoped invitation acceptance. One endpoint cannot be reassigned to a second accepted account. Existing private history is disclosed only by explicit invitation and acceptance.
- Expiring 30-minute single-use password reset tokens stored only as SHA-256 digests; SMTP TLS supported. Reset links use configured PUBLIC_URL, not an attacker-supplied Host header.
- Immutable financial records at ORM and database levels; transaction locks, unique idempotency keys, request/attachment fingerprints, source references and audit records.
- Upload cap 8 MiB; randomized filenames; supported image decoding/re-encoding to WebP; decompression pixel limit; PDF header/EOF checks; private delivery and authorization. PDFs download as attachments with restrictive sandbox CSP rather than executing inline. The application is not an antivirus scanner; PDF content safety is not guaranteed.
- Escaped Jinja content; no raw user HTML; nosniff, no framing, same-origin referrer policy, no-store authenticated responses. Financial data is not saved into service-worker cache.

## Deployment requirements

Use HTTPS and set COOKIE_SECURE=true. Keep `.env`, database dumps and receipt backups out of public directories and version control. Run app containers as the supplied non-root user. PostgreSQL and upload directories are not published by Nginx. Restrict VPS access and keep dependencies/images patched.

The CSP permits inline theme bootstrap/styles and Alpine expression evaluation (`unsafe-eval`). This is a documented hardening tradeoff, not a claim of strict CSP protection. User text is still escaped. Moving to Alpine's CSP-compatible build and externalizing inline scripts is a future defense-in-depth improvement.

## Manual phone verification

Only an administrator with server access may run:

```text
docker compose exec app flask --app settlebook:create_app verify-phone +61400111222 --evidence "support-case-123 ownership checked"
```

The command records the evidence reference in the audit log. Do not mark numbers verified merely because someone typed them. SMS verification can later replace the administrative check with a short-lived, rate-limited, single-use OTP challenge; retain explicit financial-sharing consent.

## Recovery and deactivation

SMTP must be configured for self-service reset. Missing SMTP yields a clear configuration error; reset tokens are never displayed or logged. Deactivation retains financial history for authorized counterparties, blocks sign-in, and invalidates sessions. Administrative reactivation requires independent identity verification and an audited maintenance change; there is no public reactivation shortcut.

## Verification limits

The supplied multi-user IDOR, trigger, token, rate-limit, transaction rollback and concurrency tests require PostgreSQL. They were not executed in the authoring workspace. This document states implemented controls, not a completed penetration test or production-security certification.
