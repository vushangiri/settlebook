"""Render production Jinja templates with synthetic data for visual QA, not functional verification."""

import sys
from pathlib import Path
from datetime import date
import shutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import g, render_template
from settlebook import create_app
from settlebook.models import (
    User,
    Person,
    Relationship,
    Ledger,
    Group,
    Member,
    Expense,
    Share,
    Invitation,
    Notification,
    now,
)


def render(output):
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    app = create_app({"SECRET_KEY": "visual-fixtures-only-not-a-production-secret", "WTF_CSRF_ENABLED": False})
    u = User(
        id="owner",
        name="Bhushan Giri",
        phone="+61400111222",
        email="bhushan@example.com",
        verified=True,
        active=True,
        theme="system",
    )
    me = Person(id="a", owner_id="owner", name="Bhushan Giri", is_self=True)
    a = Person(id="b", owner_id="owner", name="Sahil Sharma", phone="+61400222333", is_self=False)
    b = Person(id="c", owner_id="owner", name="Priya Patel", is_self=False)
    c = Person(id="d", owner_id="owner", name="Alex Morgan", is_self=False)
    ps = [me, a, b, c]
    rels = [Relationship(id="r" + p.id, owner_id=u.id, left_id=me.id, right_id=p.id) for p in ps[1:]]
    rows = [
        dict(r=r, name=p.name, balance=n, shared=True, side=me.id)
        for r, p, n in zip(rels, ps[1:], [8500, -4200, 12000])
    ]
    entries = [
        Ledger(
            id="e" + str(i),
            relationship_id=r.id,
            actor_id=u.id,
            cents=n,
            description=desc,
            kind=kind,
            date=date(2026, 10, 28 - i),
            created_at=now(),
            source="personal",
        )
        for i, (r, n, desc, kind) in enumerate(
            zip(
                rels,
                [8500, -4200, 12000],
                ["Dinner last Friday", "Coffee and snacks", "Tickets"],
                ["given", "taken", "given"],
            )
        )
    ]
    group = Group(
        id="g", owner_id=u.id, name="Weekend Getaway", description="A weekend with friends", status="review", revision=3
    )
    members = [
        Member(id="m" + p.id, group_id="g", person_id=p.id, user_id=u.id if p.is_self else None, accepted=p.is_self)
        for p in ps
    ]
    expense = Expense(
        id="ex",
        owner_id=u.id,
        group_id="g",
        payer_id=a.id,
        description="Accommodation",
        notes="Two nights",
        cents=18000,
        method="equal",
        date=date(2026, 10, 28),
        active=True,
    )
    state = {
        "paid": {"a": 0, "b": 18000, "c": 0, "d": 0},
        "owed": {"a": 4500, "b": 4500, "c": 4500, "d": 4500},
        "total": 18000,
        "net": {"a": -4500, "b": 13500, "c": -4500, "d": -4500},
        "expenses": [{"id": "ex"}],
        "transfers": [("a", "b", 4500), ("c", "b", 4500), ("d", "b", 4500)],
    }
    cases = {
        "home": ("home.html", dict(rows=rows, pos=20500, neg=4200, recent=entries)),
        "people": ("people.html", dict(rows=rows)),
        "person": (
            "relationship.html",
            dict(r=rels[0], ps=[me, a], side="a", balance=8500, entries=entries[:1], more=False, page=1, reviews=[]),
        ),
        "add": ("add.html", dict(rows=rows, persons=ps, selected="rb")),
        "split": ("expense_form.html", dict(persons=ps, g=None, expense=None)),
        "groups": ("groups.html", dict(groups=[group], persons=ps)),
        "group": (
            "group.html",
            dict(
                g=group,
                members=members,
                ps={p.id: p for p in ps},
                state=state,
                expenses=[expense],
                disputes=[],
                reviews=[],
                persons=ps,
            ),
        ),
        "group-expense": ("expense_form.html", dict(persons=ps, g=group, expense=None)),
        "activity": ("activity.html", dict(entries=entries, rows=rows, more=False, next_url="")),
        "profile": ("profile.html", {}),
        "login": ("auth.html", dict(mode="login")),
        "register": ("auth.html", dict(mode="register")),
        "search": ("search.html", dict(results=[("Accommodation", "/bill/ex"), ("Sahil Sharma", "/people")])),
        "bill": ("bill.html", dict(e=expense, payer=a, shares=[(Share(cents=4500), p) for p in ps])),
        "invitations": (
            "invitations.html",
            dict(
                senders={"other": "Sahil Sharma"},
                invitations=[
                    Invitation(
                        id="i",
                        sender_id="other",
                        target_id=u.id,
                        status="pending",
                        expires_at=now(),
                        relationship_id="rb",
                    )
                ],
            ),
        ),
        "notifications": (
            "notifications.html",
            dict(
                notifications=[
                    Notification(
                        id="n", message="Group review requested", path="/group/g", read=False, created_at=now()
                    )
                ]
            ),
        ),
    }
    for name, (template, context) in cases.items():
        with app.test_request_context("/" + name):
            g._login_user = u
            html = render_template(template, **context)
            # Freeze transitions for deterministic screenshot capture only.
            html = html.replace(
                "</head>", "<style>*{animation:none!important;transition:none!important}</style></head>"
            )
            (out / (name + ".html")).write_text(html)
    shutil.copytree(Path(app.static_folder), out / "static", dirs_exist_ok=True)
    links = "".join(f'<li><a href="{name}.html">{name}</a></li>' for name in cases)
    (out / "index.html").write_text(
        '<!doctype html><meta name="viewport" content="width=device-width"><h1>Settlebook template visual QA</h1><p>Synthetic fixtures; these pages do not verify persistence.</p><ul>'
        + links
        + "</ul>"
    )
    return len(cases)


if __name__ == "__main__":
    print(render(sys.argv[1]))
