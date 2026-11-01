# Deployment and recovery

## Local startup

Use README instructions. Database startup and migrations precede app traffic. Compiled CSS and vendored JavaScript are included, so Docker does not need a Node build step. Database and uploads use separate persistent named volumes. Restarting/rebuilding containers preserves both. Never use `docker compose down -v` on a deployment containing valuable records.

## Temporary HTTP deployment

Set these values in the VPS `.env`, using the address you open in your browser:

```dotenv
PUBLIC_URL=http://your-server-address
COOKIE_SECURE=false
```

The production override honors `COOKIE_SECURE` and defaults to `true` when it is unset. Secure cookies are not sent by browsers over HTTP on a VPS, which causes CSRF session token errors. Keep CSRF protection enabled.

After copying updated source and configuration to the VPS, rebuild and recreate the app and proxy:

```bash
docker compose -f compose.yaml -f compose.production.yaml up -d --build --force-recreate app nginx
```

Clear the site's browser cookies and reload the registration page before submitting again. When enabling HTTPS, set `PUBLIC_URL=https://your-domain` and `COOKIE_SECURE=true`, then recreate the containers again. HTTP transmits passwords and session cookies without encryption.

## Ubuntu VPS with HTTPS

1. Configure DNS for your domain and install Docker Engine, Compose, host Nginx and Certbot through your normal supported Ubuntu repositories.
2. Copy the source to a private directory. Configure `.env` with random secrets, `PUBLIC_URL=https://settlebook.example.com`, `COOKIE_SECURE=true` and SMTP if recovery is required.
3. Run migrations, then start with the production override:

```bash
docker compose up -d db
docker compose build
docker compose --profile tools run --rm migrate
docker compose -f compose.yaml -f compose.production.yaml up -d app nginx
```

4. Host Nginx terminates TLS and proxies to the loopback-only internal Nginx on 8080. Example server configuration before Certbot adds certificates:

```nginx
server {
    listen 80;
    server_name settlebook.example.com;
    client_max_body_size 9m;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

5. Validate Nginx config, reload it, and obtain certificates using `sudo certbot --nginx -d settlebook.example.com`. Enable HTTP-to-HTTPS redirection. Verify renewal using `sudo certbot renew --dry-run`.
6. Confirm `/health`, cookies, reset URLs, receipt downloads and mobile installation over HTTPS. The app does not trust forwarded scheme or host for reset URLs; PUBLIC_URL is authoritative.

The internal Nginx overwrites client IP forwarding. With an additional host proxy, rate limiting conservatively groups users under the host proxy's IP. For per-client IP limiting, explicitly configure a trusted real-IP chain restricted to the host gateway; never trust arbitrary client headers. The default remains safe but can over-limit multiple users. Do not expose the app or PostgreSQL ports to the internet.

## Phone verification and recovery configuration

See SECURITY.md for the CLI verification procedure. SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM and SMTP_TLS control recovery delivery. Test against a development mailbox first. No SMS or paid push service is required. Notifications are in-app; browser push is not included because it is optional in the specification.

## Backups (PowerShell and Bash)

Create a `backups` directory. Generate the binary database dump inside the container, then copy it out. Avoid piping a binary `pg_dump` through Windows PowerShell redirection.

```text
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/settlebook.dump'
docker compose cp db:/tmp/settlebook.dump ./backups/settlebook.dump
docker compose exec -T app tar -czf /tmp/settlebook-uploads.tar.gz -C /data uploads
docker compose cp app:/tmp/settlebook-uploads.tar.gz ./backups/settlebook-uploads.tar.gz
```

For a consistent database/file pair, pause app traffic during both backups. Retain source/image version, `.env` securely, and a dated backup manifest. Encrypt/off-site-store backups according to your needs; never publish them.

## Restore drill

Restore into an isolated environment first. To restore an intentionally selected deployment, stop app/nginx, copy the dump into the database container, then run:

```text
docker compose stop app nginx
docker compose cp ./backups/settlebook.dump db:/tmp/restore.dump
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists /tmp/restore.dump'
```

Restore uploads into the attachments volume using a one-off app container:

```text
docker compose run --rm --no-deps -v ./backups:/backup:ro app tar -xzf /backup/settlebook-uploads.tar.gz -C /data
docker compose up -d app nginx
```

`--clean` intentionally replaces database objects. Confirm the selected deployment and tested backup before running it. Existing uploads with matching randomized names are replaced; restore into a fresh volume for an exact recovery drill. Inspect health, balances, attachments, migrations and shared permissions after restore.

## Upgrade and rollback

Back up database/uploads, stop traffic, retain the currently working image/source, build the new version, run migration, then start app/nginx. Run smoke tests before reopening traffic. If only application code changed, return to the previous image. If schema changed incompatibly, restore the matching backup and previous image together; do not run an unsupported destructive migration downgrade.

## Operations

```text
docker compose ps
docker compose logs --tail=100 app nginx db
docker compose exec app flask --app settlebook:create_app cleanup-uploads
```

The cleanup command removes only filesystem objects missing from the attachment table and older than 24 hours. It does not delete financial attachments. Schedule it with the operating system's timer/cron if needed. Check disk capacity, database backups, TLS renewal and failed auth attempts. Runtime logs must not contain passwords/reset tokens; do not enable Flask debug in production.

## Limits still requiring execution

The authoring workspace did not have Docker or PostgreSQL. Image builds, full Compose startup, pg_trgm installation, backup/restore, real SMTP and TLS installation were not executed there. Follow TESTING.md before relying on this deployment.
