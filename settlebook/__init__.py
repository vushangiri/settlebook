import os
from datetime import timedelta
from pathlib import Path
import click
from flask import Flask, session, request
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
from .models import db, User, Audit

login = LoginManager()
csrf = CSRFProtect()


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "DATABASE_URL", "postgresql+psycopg://settlebook:localonly@localhost:5432/settlebook"
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
        UPLOAD_FOLDER=os.environ.get("UPLOAD_FOLDER", "/tmp/settlebook-uploads"),
        MAX_CONTENT_LENGTH=9 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "true").lower() == "true",
        PERMANENT_SESSION_LIFETIME=timedelta(days=7),
        WTF_CSRF_TIME_LIMIT=8 * 60 * 60,
        PUBLIC_URL=os.environ.get("PUBLIC_URL", "http://localhost:8080"),
        SMTP_HOST=os.environ.get("SMTP_HOST"),
        SMTP_PORT=int(os.environ.get("SMTP_PORT", "587")),
        SMTP_USER=os.environ.get("SMTP_USER"),
        SMTP_PASSWORD=os.environ.get("SMTP_PASSWORD"),
        SMTP_FROM=os.environ.get("SMTP_FROM", "settlebook@localhost"),
        SMTP_TLS=os.environ.get("SMTP_TLS", "true").lower() == "true",
    )
    if config:
        app.config.update(config)
    app.config["ASSET_VERSION"] = str(
        max(p.stat().st_mtime_ns for p in Path(app.static_folder).rglob("*") if p.is_file())
    )

    @app.context_processor
    def asset_context():
        return {"asset_version": app.config["ASSET_VERSION"]}
    if not app.config["SECRET_KEY"] or len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError("Set SECRET_KEY to at least 32 random characters.")
    if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
        raise RuntimeError("PostgreSQL is required; SQLite is not supported.")
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    if os.environ.get("TRUST_PROXY") == "true":
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
    db.init_app(app)
    login.init_app(app)
    csrf.init_app(app)
    Migrate(app, db)
    login.login_view = "web.login_page"

    @login.user_loader
    def load_user(ident):
        user = db.session.get(User, ident)
        return user if user and user.active and session.get("sv") == user.session_version else None

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        )
        if app.config["SESSION_COOKIE_SECURE"]:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        if not request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        elif request.args.get("v") == app.config["ASSET_VERSION"]:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    @app.template_filter("cash")
    def cash(n):
        n = int(n or 0)
        sign = "-" if n < 0 else ""
        return f"{sign}${abs(n) // 100:,}.{abs(n) % 100:02d}"

    from .routes import web

    app.register_blueprint(web)

    @app.cli.command("verify-phone")
    @click.argument("phone")
    @click.option(
        "--evidence",
        required=True,
        help="Reference to the independently checked ownership evidence; do not include secret documents.",
    )
    def verify_phone(phone, evidence):
        """Administrator-only out-of-band command. Never infer verification from signup."""
        user = db.session.scalar(db.select(User).where(User.phone == phone))
        if not user:
            raise click.ClickException("User not found; use normalized E.164.")
        user.verified = True
        db.session.add(
            Audit(actor_id=user.id, action="admin.phone.verify", target_id=user.id, data={"evidence": evidence})
        )
        db.session.commit()
        click.echo("Phone marked verified after administrator review.")

    @app.cli.command("cleanup-uploads")
    def cleanup_uploads():
        """Delete files not referenced by attachment rows, older than 24 hours."""
        import time
        from .models import Attachment

        known = set(db.session.scalars(db.select(Attachment.stored)))
        for p in Path(app.config["UPLOAD_FOLDER"]).iterdir():
            if p.is_file() and p.name not in known and p.stat().st_mtime < time.time() - 86400:
                p.unlink()

    return app
