import os
import pytest
from sqlalchemy import text
from flask_migrate import upgrade
from settlebook import create_app
from settlebook.models import db


@pytest.fixture
def app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-with-at-least-32-characters",
            "WTF_CSRF_ENABLED": False,
            "SESSION_COOKIE_SECURE": False,
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
        }
    )


@pytest.fixture
def pgapp(tmp_path):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("BLOCKED: TEST_DATABASE_URL is not set; disposable PostgreSQL required.")
    if "test" not in url.rsplit("/", 1)[-1]:
        pytest.fail("TEST_DATABASE_URL must reference a database whose name includes test.")
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-with-at-least-32-characters",
            "WTF_CSRF_ENABLED": False,
            "SESSION_COOKIE_SECURE": False,
            "SQLALCHEMY_DATABASE_URI": url,
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
        }
    )
    with app.app_context():
        # The supplied URL is explicitly a disposable test database, never production.
        db.session.execute(text("DROP SCHEMA public CASCADE"))
        db.session.execute(text("CREATE SCHEMA public"))
        db.session.commit()
        upgrade(directory="migrations")
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()
