import json
from pathlib import Path
import pytest
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql
from settlebook import create_app
from settlebook.models import db


def test_postgres_only():
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        create_app({"SECRET_KEY": "x" * 40, "SQLALCHEMY_DATABASE_URI": "sqlite://"})


def test_all_model_ddl_compiles():
    for table in db.metadata.sorted_tables:
        assert "CREATE TABLE" in str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert {
        "user",
        "person",
        "relationship",
        "access",
        "ledger",
        "group",
        "member",
        "expense",
        "share",
        "snapshot",
        "transfer",
        "review",
        "operation",
        "audit",
        "invitation",
        "attachment",
        "notification",
        "reset_token",
        "rate_bucket",
    } == set(db.metadata.tables)


def test_templates_compile(app):
    for name in app.jinja_env.list_templates():
        app.jinja_env.get_template(name)


def test_public_auth_and_security_headers(app):
    c = app.test_client()
    for path in ["/login", "/register", "/forgot"]:
        r = c.get(path)
        assert r.status_code == 200
        assert b"csrf_token" in r.data
        assert r.headers["Cache-Control"] == "no-store"
        assert r.headers["X-Frame-Options"] == "DENY"
    assert c.get("/").status_code == 302


def test_csrf_without_database(app):
    app.config["WTF_CSRF_ENABLED"] = True
    assert app.test_client().post("/register", data={"name": "No CSRF"}).status_code == 400


def test_csrf_token_lifetime(app, monkeypatch):
    from flask_wtf.csrf import generate_csrf, validate_csrf
    from wtforms.validators import ValidationError
    import time

    with app.test_request_context("/register", method="POST"):
        issued_at = time.time()
        token = generate_csrf()
        validate_csrf(token)

        monkeypatch.setattr("itsdangerous.timed.time.time", lambda: issued_at + 8 * 60 * 60 + 1)
        with pytest.raises(ValidationError, match="expired"):
            validate_csrf(token)


def test_offline_shell_never_caches_private_data():
    source = Path("settlebook/static/sw.js").read_text()
    assert "e.request.method!=='GET'" in source
    assert "caches.put" not in source
    assert "ASSETS.includes(u.pathname)" in source


def test_manifest_assets(app):
    manifest = json.loads(Path("settlebook/static/manifest.webmanifest").read_text())
    assert manifest["display"] == "standalone"
    for icon in manifest["icons"]:
        assert app.test_client().get(icon["src"]).status_code == 200
    assert app.test_client().get("/sw.js").headers["Service-Worker-Allowed"] == "/"


def test_render_all_main_screens(tmp_path):
    from tools.render_fixtures import render

    assert render(tmp_path / "screens") == 16
    for page in (tmp_path / "screens").glob("*.html"):
        assert "<h" in page.read_text()
