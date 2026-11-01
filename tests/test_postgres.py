"""Real migrations and PostgreSQL only. No SQLite or mocked persistence."""

import io
import secrets
from concurrent.futures import ThreadPoolExecutor
import pytest
from PIL import Image
from sqlalchemy import select, func, text
from werkzeug.security import generate_password_hash
from settlebook.models import db, User, Person, Relationship, Ledger, Group, Expense, Review, Notification
from settlebook import services as s

pytestmark = pytest.mark.postgres


def seed(app):
    with app.app_context():
        u = User(
            name="Owner",
            phone="+61400111222",
            email="owner@example.com",
            password_hash=generate_password_hash("a-secure-password"),
            verified=True,
        )
        v = User(
            name="Other",
            phone="+61400222333",
            email="other@example.com",
            password_hash=generate_password_hash("a-secure-password"),
            verified=True,
        )
        z = User(name="Stranger", phone="+61400333444", password_hash=generate_password_hash("a-secure-password"))
        db.session.add_all([u, v, z])
        db.session.flush()
        me = Person(owner_id=u.id, name="Owner", is_self=True)
        other_self = Person(owner_id=v.id, name="Other", is_self=True)
        stranger_self = Person(owner_id=z.id, name="Stranger", is_self=True)
        a = Person(owner_id=u.id, name="Other", phone=v.phone)
        b = Person(owner_id=u.id, name="Local")
        db.session.add_all([me, other_self, stranger_self, a, b])
        db.session.flush()
        r = s.relation(u, me.id, a.id)
        ids = {"u": u.id, "v": v.id, "z": z.id, "me": me.id, "a": a.id, "b": b.id, "r": r.id}
        db.session.commit()
        return ids


def client(app, uid):
    c = app.test_client()
    with app.app_context():
        version = db.session.get(User, uid).session_version
    with c.session_transaction() as session:
        session["_user_id"] = uid
        session["_fresh"] = True
        session["sv"] = version
    return c


def call(c, action, data, key=None):
    return c.post("/action/" + action, json=data, headers={"Idempotency-Key": key or secrets.token_hex(16)})


def entry_data(ids, **kwargs):
    d = {
        "relationship_id": ids["r"],
        "kind": "given",
        "amount": "100.00",
        "date": "2026-11-01",
        "description": "Dinner",
    }
    d.update(kwargs)
    return d


def new_group(c, ids):
    r = call(c, "group", {"name": "Trip", "participants": [ids["a"], ids["b"]]})
    assert r.status_code == 200, r.json
    return r.json["id"]


def expense(c, ids, gid=None, **kwargs):
    d = {
        "payer_id": ids["a"],
        "participants": [ids["me"], ids["a"], ids["b"]],
        "method": "equal",
        "amount": "90",
        "date": "2026-11-01",
        "description": "Dinner",
    }
    if gid:
        d["group_id"] = gid
    d.update(kwargs)
    r = call(c, "expense", d)
    assert r.status_code == 200, r.json
    return r.json["id"]


def test_post_repay_reverse_and_idempotency(pgapp):
    ids = seed(pgapp)
    c = client(pgapp, ids["u"])
    d = entry_data(ids)
    first = call(c, "entry", d, "same-key-0001")
    assert first.status_code == 200
    assert call(c, "entry", d, "same-key-0001").json == first.json
    assert call(c, "entry", entry_data(ids, amount="101"), "same-key-0001").status_code == 409
    assert call(c, "entry", entry_data(ids, kind="repayment_received", amount="30")).status_code == 200
    assert call(c, "entry", entry_data(ids, kind="repayment_received", amount="80")).status_code == 400
    with pgapp.app_context():
        assert s.balance(db.session.get(Relationship, ids["r"]), ids["me"]) == 7000
    assert (
        call(
            c, "reverse", {"entry_id": first.json["id"], "date": "2026-11-01", "description": "Correction"}
        ).status_code
        == 200
    )
    assert (
        call(c, "reverse", {"entry_id": first.json["id"], "date": "2026-11-01", "description": "Again"}).status_code
        == 409
    )


def test_shared_opposite_perspective_and_idor(pgapp):
    ids = seed(pgapp)
    a = client(pgapp, ids["u"])
    b = client(pgapp, ids["v"])
    z = client(pgapp, ids["z"])
    call(a, "entry", entry_data(ids))
    assert b.get("/relationship/" + ids["r"]).status_code == 403
    inv = call(a, "invite", {"person_id": ids["a"], "relationship_id": ids["r"]})
    assert inv.status_code == 200
    assert call(z, "accept", {"invitation_id": inv.json["id"], "accept": "yes"}).status_code == 403
    assert call(b, "accept", {"invitation_id": inv.json["id"], "accept": "yes"}).status_code == 200
    with pgapp.app_context():
        r = db.session.get(Relationship, ids["r"])
        assert s.balance(r, ids["me"]) == -s.balance(r, ids["a"]) == 10000
    assert b.get("/relationship/" + ids["r"]).status_code == 200
    assert call(z, "entry", entry_data(ids)).status_code == 403
    assert ("/relationship/" + ids["r"]).encode() not in z.get("/search?q=Dinner").data


def test_split_third_party_and_atomic_invalid(pgapp):
    ids = seed(pgapp)
    c = client(pgapp, ids["u"])
    eid = expense(c, ids)
    with pgapp.app_context():
        es = db.session.scalars(select(Ledger).where(Ledger.source_id == eid)).all()
        assert len(es) == 2
        pairs = {
            frozenset(
                (
                    db.session.get(Relationship, e.relationship_id).left_id,
                    db.session.get(Relationship, e.relationship_id).right_id,
                )
            )
            for e in es
        }
        assert frozenset((ids["a"], ids["b"])) in pairs
    bad = call(
        c,
        "expense",
        {
            "payer_id": ids["me"],
            "participants": [ids["a"]],
            "amount": "90",
            "method": "custom",
            "shares": {ids["a"]: "89"},
            "date": "2026-11-01",
        },
    )
    assert bad.status_code == 400
    with pgapp.app_context():
        assert db.session.scalar(select(func.count()).select_from(Expense)) == 1


def test_group_isolation_finalization_retry_freeze(pgapp):
    ids = seed(pgapp)
    c = client(pgapp, ids["u"])
    g = new_group(c, ids)
    expense(c, ids, g)
    with pgapp.app_context():
        assert db.session.scalar(select(func.count()).select_from(Ledger)) == 0
    assert call(c, "group-status", {"group_id": g, "status": "review"}).status_code == 200
    with pgapp.app_context():
        rev = db.session.get(Group, g).revision
    d = {"group_id": g, "revision": rev, "confirm": "yes"}
    assert call(c, "finalize", d).status_code == 200
    assert call(c, "finalize", d).status_code == 200
    with pgapp.app_context():
        assert db.session.scalar(select(func.count()).select_from(Ledger)) == 2
    r = call(
        c,
        "expense",
        {"group_id": g, "payer_id": ids["a"], "participants": [ids["me"]], "amount": "10", "date": "2026-11-01"},
    )
    assert r.status_code == 409


def test_dispute_blocks_group_and_resolution(pgapp):
    ids = seed(pgapp)
    c = client(pgapp, ids["u"])
    g = new_group(c, ids)
    eid = expense(c, ids, g)
    r = call(c, "review", {"expense_id": eid, "status": "disputed", "note": "Wrong allocation"})
    assert r.status_code == 200
    call(c, "group-status", {"group_id": g, "status": "review"})
    with pgapp.app_context():
        rev = db.session.get(Group, g).revision
        rid = db.session.scalar(select(Review.id).where(Review.expense_id == eid))
    assert call(c, "finalize", {"group_id": g, "revision": rev, "confirm": "yes"}).status_code == 409
    assert (
        call(
            c, "review", {"expense_id": eid, "status": "resolved", "note": "Checked receipt", "resolves_id": rid}
        ).status_code
        == 200
    )
    assert call(c, "finalize", {"group_id": g, "revision": rev, "confirm": "yes"}).status_code == 200


def test_expense_correction_retains_history(pgapp):
    ids = seed(pgapp)
    c = client(pgapp, ids["u"])
    g = new_group(c, ids)
    eid = expense(c, ids, g)
    replacement = expense(c, ids, g, amount="120", replaces_id=eid)
    with pgapp.app_context():
        assert not db.session.get(Expense, eid).active
        assert db.session.get(Expense, replacement).replaces_id == eid
        assert s.group_state(db.session.get(Group, g))["total"] == 12000


def test_database_trigger_prevents_mutation(pgapp):
    ids = seed(pgapp)
    c = client(pgapp, ids["u"])
    call(c, "entry", entry_data(ids))
    with pgapp.app_context():
        with pytest.raises(Exception):
            db.session.execute(text("UPDATE ledger SET cents=1"))
            db.session.commit()
        db.session.rollback()
        assert abs(db.session.scalar(select(Ledger.cents))) == 10000


def test_attachment_security_and_notifications(pgapp):
    ids = seed(pgapp)
    c = client(pgapp, ids["u"])
    z = client(pgapp, ids["z"])
    image = io.BytesIO()
    Image.new("RGB", (20, 20), "red").save(image, format="PNG")
    image.seek(0)
    d = entry_data(ids)
    d["key"] = "upload-key-0001"
    d["file"] = (image, "receipt.png")
    r = c.post("/action/entry", data=d, content_type="multipart/form-data")
    assert r.status_code == 302
    with pgapp.app_context():
        aid = db.session.scalar(select(Ledger.attachment_id))
        assert db.session.scalar(select(func.count()).select_from(Notification)) > 0
    assert c.get("/attachment/" + aid).status_code == 200
    assert z.get("/attachment/" + aid).status_code == 403
    revision = c.get("/api/sync").json["revision"]
    assert not c.get("/api/sync?revision=" + revision).json["changed"]
    assert c.get("/search?q=Dinner").status_code == 200


def test_registration_login_profile_and_session_invalidation(pgapp):
    c = pgapp.test_client()
    d = {"name": "New User", "phone": "+61400999888", "email": "new@example.com", "password": "my-secure-password"}
    assert c.post("/register", data=d).status_code == 302
    assert c.get("/profile").status_code == 200
    c.post("/logout")
    assert c.get("/profile").status_code == 302
    assert c.post("/login", data={"phone": d["phone"], "password": d["password"]}).status_code == 302
    second = pgapp.test_client()
    second.post("/login", data={"phone": d["phone"], "password": d["password"]})
    assert (
        c.post(
            "/profile", data={**d, "current_password": d["password"], "password": "a-new-secure-password"}
        ).status_code
        == 302
    )
    assert second.get("/profile").status_code == 302


@pytest.mark.concurrency
def test_concurrent_duplicate_post(pgapp):
    ids = seed(pgapp)

    def run(_):
        return call(client(pgapp, ids["u"]), "entry", entry_data(ids), "concurrent-0001").status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(run, range(4))) == [200] * 4
    with pgapp.app_context():
        assert db.session.scalar(select(func.count()).select_from(Ledger)) == 1


@pytest.mark.concurrency
def test_concurrent_partial_repayments_cannot_overpay(pgapp):
    ids = seed(pgapp)
    call(client(pgapp, ids["u"]), "entry", entry_data(ids))

    def run(_):
        return call(
            client(pgapp, ids["u"]), "entry", entry_data(ids, kind="repayment_received", amount="70")
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert sorted(results) == [200, 400]
    with pgapp.app_context():
        assert s.balance(db.session.get(Relationship, ids["r"]), ids["me"]) == 3000


@pytest.mark.concurrency
def test_concurrent_finalize_once(pgapp):
    ids = seed(pgapp)
    c = client(pgapp, ids["u"])
    g = new_group(c, ids)
    expense(c, ids, g)
    call(c, "group-status", {"group_id": g, "status": "review"})
    with pgapp.app_context():
        rev = db.session.get(Group, g).revision

    def run(_):
        return call(client(pgapp, ids["u"]), "finalize", {"group_id": g, "revision": rev, "confirm": "yes"}).status_code

    with ThreadPoolExecutor(max_workers=3) as pool:
        assert list(pool.map(run, range(3))) == [200] * 3
    with pgapp.app_context():
        assert db.session.scalar(select(func.count()).select_from(Ledger)) == 2


def test_shared_user_split_reuses_existing_relationship(pgapp):
    ids = seed(pgapp)
    a = client(pgapp, ids["u"])
    b = client(pgapp, ids["v"])
    inv = call(a, "invite", {"person_id": ids["a"], "relationship_id": ids["r"]})
    assert call(b, "accept", {"invitation_id": inv.json["id"], "accept": "yes"}).status_code == 200
    with pgapp.app_context():
        bs = s.own_person(db.session.get(User, ids["v"])).id
    r = call(
        b,
        "expense",
        {
            "payer_id": bs,
            "participants": [bs, ids["me"]],
            "amount": "50",
            "method": "equal",
            "date": "2026-11-01",
            "description": "Shared by other party",
        },
    )
    assert r.status_code == 200, r.json
    with pgapp.app_context():
        assert db.session.scalar(select(func.count()).select_from(Relationship)) == 1
        assert s.balance(db.session.get(Relationship, ids["r"]), ids["me"]) == -2500


def test_third_party_repayment(pgapp):
    ids = seed(pgapp)
    c = client(pgapp, ids["u"])
    expense(c, ids)
    with pgapp.app_context():
        r = db.session.scalar(
            select(Relationship).where(
                Relationship.left_id.in_([ids["a"], ids["b"]]), Relationship.right_id.in_([ids["a"], ids["b"]])
            )
        )
        rid = r.id
    response = call(
        c,
        "entry",
        {
            "relationship_id": rid,
            "perspective_id": ids["a"],
            "kind": "repayment_received",
            "amount": "10",
            "date": "2026-11-01",
            "description": "Local paid Other",
        },
    )
    assert response.status_code == 200, response.json
    with pgapp.app_context():
        assert s.balance(db.session.get(Relationship, rid), ids["a"]) == 2000


def test_reset_expiry_single_use_and_sessions(pgapp, monkeypatch):
    from settlebook.models import ResetToken, now
    from datetime import timedelta
    from settlebook import routes

    seed(pgapp)
    c = pgapp.test_client()
    captured = []
    pgapp.config["SMTP_HOST"] = "test-only"
    monkeypatch.setattr(routes, "send_reset", lambda u, raw: captured.append(raw))
    assert c.post("/forgot", data={"email": "owner@example.com"}).status_code == 302
    raw = captured.pop()
    assert c.post("/reset/" + raw, data={"password": "updated-secure-password"}).status_code == 302
    assert c.post("/reset/" + raw, data={"password": "another-secure-password"}).status_code == 400
    c.post("/forgot", data={"email": "owner@example.com"})
    raw = captured.pop()
    with pgapp.app_context():
        token = db.session.scalar(select(ResetToken).where(ResetToken.used.is_(False)))
        token.expires_at = now() - timedelta(seconds=1)
        db.session.commit()
    assert c.post("/reset/" + raw, data={"password": "another-secure-password"}).status_code == 400


def test_failed_financial_transaction_rolls_back_everything(pgapp, monkeypatch):
    ids = seed(pgapp)
    c = client(pgapp, ids["u"])

    def fail(*args, **kwargs):
        raise RuntimeError("Injected after ledger flush")

    with pgapp.app_context():
        from settlebook.models import Audit
        initial_audits = db.session.scalar(select(func.count()).select_from(Audit))
    monkeypatch.setattr(s, "notify", fail)
    assert call(c, "entry", entry_data(ids), "rollback-key-0001").status_code == 500
    with pgapp.app_context():
        from settlebook.models import Operation, Audit

        assert db.session.scalar(select(func.count()).select_from(Ledger)) == 0
        assert db.session.scalar(select(func.count()).select_from(Operation)) == 0
        assert db.session.scalar(select(func.count()).select_from(Audit)) == initial_audits


def test_full_repayment_and_stale_finalization(pgapp):
    ids = seed(pgapp)
    c = client(pgapp, ids["u"])
    call(c, "entry", entry_data(ids))
    assert call(c, "entry", entry_data(ids, kind="repayment_received", amount="100")).status_code == 200
    with pgapp.app_context():
        assert s.balance(db.session.get(Relationship, ids["r"]), ids["me"]) == 0
    g = new_group(c, ids)
    expense(c, ids, g)
    call(c, "group-status", {"group_id": g, "status": "review"})
    assert call(c, "finalize", {"group_id": g, "revision": 0, "confirm": "yes"}).status_code == 409


def test_rate_limiting_and_unverified_sharing(pgapp):
    ids = seed(pgapp)
    a = client(pgapp, ids["u"])
    b = client(pgapp, ids["v"])
    inv = call(a, "invite", {"person_id": ids["a"], "relationship_id": ids["r"]})
    with pgapp.app_context():
        db.session.get(User, ids["v"]).verified = False
        db.session.commit()
    assert call(b, "accept", {"invitation_id": inv.json["id"], "accept": "yes"}).status_code == 200
    c = pgapp.test_client()
    for _ in range(15):
        assert c.post("/login", data={"phone": "+61400111222", "password": "wrong"}).status_code == 400
    assert c.post("/login", data={"phone": "+61400111222", "password": "wrong"}).status_code == 429


@pytest.mark.concurrency
def test_opposite_users_concurrent_repayments(pgapp):
    ids = seed(pgapp)
    a = client(pgapp, ids["u"])
    b = client(pgapp, ids["v"])
    inv = call(a, "invite", {"person_id": ids["a"], "relationship_id": ids["r"]})
    call(b, "accept", {"invitation_id": inv.json["id"], "accept": "yes"})
    call(a, "entry", entry_data(ids))

    def run(side):
        uid, kind = (ids["u"], "repayment_received") if side == 0 else (ids["v"], "repayment_made")
        return call(client(pgapp, uid), "entry", entry_data(ids, kind=kind, amount="70")).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, [0, 1]))
    assert sorted(results) == [200, 400]
    with pgapp.app_context():
        assert s.balance(db.session.get(Relationship, ids["r"]), ids["me"]) == 3000


def test_automatic_group_invitations_and_shared_updates(pgapp):
    from settlebook.models import Invitation, Member
    ids = seed(pgapp)
    a, b = client(pgapp, ids["u"]), client(pgapp, ids["v"])
    with pgapp.app_context():
        db.session.get(User, ids["v"]).verified = False
        db.session.commit()
    gid = new_group(a, ids)
    with pgapp.app_context():
        member = db.session.scalar(select(Member).where(Member.group_id == gid, Member.person_id == ids["a"]))
        inv = db.session.scalar(select(Invitation).where(Invitation.member_id == member.id))
        invitation_id = inv.id
    assert b.get("/group/" + gid).status_code == 403
    assert call(b, "accept", {"invitation_id": invitation_id, "accept": "yes"}).status_code == 200
    eid = expense(a, ids, gid)
    assert eid.encode() in b.get("/group/" + gid).data


def test_automatic_ledger_invitation_waits_for_registration(pgapp):
    from settlebook.models import Invitation
    ids = seed(pgapp)
    a = client(pgapp, ids["u"])
    response = a.post("/people", data={"name": "Future user", "phone": "+61400999888"})
    assert response.status_code == 302
    with pgapp.app_context():
        inv = db.session.scalar(select(Invitation).where(Invitation.target_phone == "+61400999888"))
        assert inv.target_id is None
        iid = inv.id
    b = pgapp.test_client()
    response = b.post("/register", data={"name": "Future user", "phone": "+61400999888", "password": "secure-password"})
    assert response.status_code == 302
    assert b"Ledger invitation" in b.get("/invitations").data
    assert call(b, "accept", {"invitation_id": iid, "accept": "yes"}).status_code == 200
