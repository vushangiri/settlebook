import hashlib
import io
import secrets
import smtplib
from datetime import date, timedelta
from email.message import EmailMessage
from pathlib import Path
import phonenumbers
from email_validator import validate_email, EmailNotValidError
from PIL import Image, UnidentifiedImageError
from flask import (
    Blueprint,
    request,
    render_template,
    redirect,
    url_for,
    flash,
    session,
    jsonify,
    current_app,
    send_file,
)
from flask_login import current_user, login_user, logout_user, login_required
from sqlalchemy import select, func, or_, case
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import Forbidden, HTTPException
from .models import (
    db,
    now,
    User,
    Person,
    Relationship,
    Access,
    Ledger,
    Group,
    Member,
    Expense,
    Share,
    Review,
    Invitation,
    Attachment,
    Notification,
    ResetToken,
    RateBucket,
)
from . import services as s

web = Blueprint("web", __name__)


def phone(value):
    try:
        p = phonenumbers.parse(value, "AU")
        if not phonenumbers.is_valid_number(p):
            raise ValueError()
        return phonenumbers.format_number(p, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        raise ValueError("Enter a valid phone number, including its country code.") from None


def email(value):
    if not value:
        return None
    try:
        return validate_email(value, check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        raise ValueError("Enter a valid email address.") from None


def password(value):
    if not 6 <= len(value) <= 200:
        raise ValueError("Use a password containing 6–200 characters.")
    return generate_password_hash(value)


def limited(scope, limit=15):
    # Do not trust arbitrary X-Forwarded-For. Nginx sets real IP through a trusted deployment boundary.
    identity = (request.remote_addr or "") + ":" + scope
    key = hashlib.sha256(identity.encode()).hexdigest()
    cutoff = now() - timedelta(minutes=15)
    q = insert(RateBucket).values(key=key, starts=now(), count=1)
    print(type(RateBucket.starts))
    q = q.on_conflict_do_update(
        index_elements=["key"],
        set_={
            "starts": case((RateBucket.starts < cutoff, now()), else_=RateBucket.starts),
            "count": case((RateBucket.starts < cutoff, 1), else_=RateBucket.count + 1),
        },
    ).returning(RateBucket.count)
    count = db.session.scalar(q)
    db.session.commit()
    if count > limit:
        from werkzeug.exceptions import TooManyRequests

        raise TooManyRequests("Too many attempts. Try again after 15 minutes.")


def data():
    if request.is_json:
        return request.get_json()
    d = request.form.to_dict()
    d["participants"] = request.form.getlist("participants")
    d["shares"] = {k[6:]: v for k, v in request.form.items() if k.startswith("share_")}
    return d


def relation_query():
    return select(Relationship).where(
        or_(
            Relationship.owner_id == current_user.id,
            Relationship.id.in_(select(Access.relationship_id).where(Access.user_id == current_user.id)),
        )
    )


def groups_query():
    return select(Group).where(
        or_(
            Group.owner_id == current_user.id,
            Group.id.in_(select(Member.group_id).where(Member.user_id == current_user.id, Member.accepted.is_(True))),
        )
    )


def ledger_query():
    return select(Ledger).where(Ledger.relationship_id.in_(relation_query().with_only_columns(Relationship.id)))


def people():
    return s.selectable_people(current_user)


def overview():
    # One aggregate query, one access query, one people query, no per-row balance lookups.
    rels = db.session.scalars(relation_query().order_by(Relationship.created_at.desc())).all()
    sums = dict(
        db.session.execute(
            select(Ledger.relationship_id, func.sum(Ledger.cents))
            .where(Ledger.relationship_id.in_([r.id for r in rels]))
            .group_by(Ledger.relationship_id)
        ).all()
    )
    accesses = {
        a.relationship_id: a.person_id
        for a in db.session.scalars(select(Access).where(Access.user_id == current_user.id))
    }
    me = s.own_person(current_user).id
    persons = {
        p.id: p
        for p in db.session.scalars(
            select(Person).where(Person.id.in_({p for r in rels for p in (r.left_id, r.right_id)}))
        )
    }
    rows = []
    pos = neg = 0
    for r in rels:
        side = accesses.get(r.id, me if me in (r.left_id, r.right_id) else None)
        amount = int(sums.get(r.id, 0)) * (1 if side == r.left_id else -1)
        title = (
            persons[r.right_id if side == r.left_id else r.left_id].name
            if side
            else persons[r.left_id].name + " ↔ " + persons[r.right_id].name
        )
        if side:
            pos += max(amount, 0)
            neg += max(-amount, 0)
        rows.append(
            {"r": r, "name": title, "balance": amount if side else None, "shared": r.id in accesses, "side": side}
        )
    return rows, pos, neg


@web.app_context_processor
def context():
    return {"today": date.today().isoformat(), "token": lambda: secrets.token_urlsafe(24), "user": current_user}


@web.app_errorhandler(Exception)
def error(exc):
    db.session.rollback()
    if isinstance(exc, HTTPException):
        code = exc.code
        message = exc.description
    elif isinstance(exc, (ValueError, KeyError, TypeError)):
        code = 400
        message = str(exc)
    elif isinstance(exc, IntegrityError):
        code = 409
        message = "This operation conflicts with an existing record. Refresh and try again."
    else:
        current_app.logger.exception("Request failed")
        code = 500
        message = "The request failed; no success has been confirmed. Retry using the same submission key."
    if request.is_json or request.path.startswith("/api/"):
        return jsonify(error=message), code
    return render_template("error.html", message=message), code


@web.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        limited("register")
        d = request.form
        name = d.get("name", "").strip()
        if not name or len(name) > 120:
            raise ValueError("A name of up to 120 characters is required.")
        u = User(
            name=name,
            phone=phone(d.get("phone", "")),
            email=email(d.get("email", "")),
            password_hash=password(d.get("password", "")),
        )
        db.session.add(u)
        db.session.flush()
        db.session.add(Person(owner_id=u.id, name=name, phone=u.phone, email=u.email, is_self=True))
        s.claim_invitations(u)
        s.audit(u, "account.register", u)
        if request.files.get("file") and request.files["file"].filename:
            u.avatar_id = store_upload(u, images_only=True).id
        db.session.commit()
        session.clear()
        login_user(u)
        session["sv"] = u.session_version
        session.permanent = True
        return redirect("/")
    return render_template("auth.html", mode="register")


@web.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        limited("login")
        u = db.session.scalar(select(User).where(User.phone == phone(request.form.get("phone", ""))))
        if not u or not u.active or not check_password_hash(u.password_hash, request.form.get("password", "")):
            raise ValueError("Invalid credentials.")
        session.clear()
        login_user(u)
        session["sv"] = u.session_version
        session.permanent = True
        return redirect("/")
    return render_template("auth.html", mode="login")


@web.post("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect("/login")


def send_reset(u, raw):
    msg = EmailMessage()
    msg["Subject"] = "Reset your Settlebook password"
    msg["From"] = current_app.config["SMTP_FROM"]
    msg["To"] = u.email
    msg.set_content(
        "Reset your password within 30 minutes: " + current_app.config["PUBLIC_URL"].rstrip("/") + "/reset/" + raw
    )
    with smtplib.SMTP(current_app.config["SMTP_HOST"], current_app.config["SMTP_PORT"], timeout=10) as smtp:
        if current_app.config["SMTP_TLS"]:
            smtp.starttls()
        if current_app.config["SMTP_USER"]:
            smtp.login(current_app.config["SMTP_USER"], current_app.config["SMTP_PASSWORD"])
        smtp.send_message(msg)


@web.route("/forgot", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        limited("reset", 5)
        if not current_app.config["SMTP_HOST"]:
            raise ValueError("Password reset delivery is not configured. Contact the administrator.")
        u = db.session.scalar(
            select(User).where(User.email == email(request.form.get("email", "")), User.active.is_(True))
        )
        if u:
            raw = secrets.token_urlsafe(32)
            db.session.add(
                ResetToken(
                    user_id=u.id,
                    digest=hashlib.sha256(raw.encode()).hexdigest(),
                    expires_at=now() + timedelta(minutes=30),
                )
            )
            send_reset(u, raw)
            db.session.commit()
        flash("If this email is registered, a reset link has been sent.")
        return redirect("/login")
    return render_template("auth.html", mode="forgot")


@web.route("/reset/<raw>", methods=["GET", "POST"])
def reset(raw):
    if request.method == "POST":
        limited("reset-token")
        t = db.session.scalar(
            select(ResetToken).where(ResetToken.digest == hashlib.sha256(raw.encode()).hexdigest()).with_for_update()
        )
        if not t or t.used or t.expires_at < now():
            raise ValueError("Invalid or expired reset link.")
        u = s.get(User, t.user_id, True)
        u.password_hash = password(request.form.get("password", ""))
        u.session_version += 1
        t.used = True
        s.audit(u, "account.reset", u)
        db.session.commit()
        session.clear()
        return redirect("/login")
    return render_template("auth.html", mode="reset")


@web.get("/")
@login_required
def home():
    rows, pos, neg = overview()
    recent = db.session.scalars(ledger_query().order_by(Ledger.created_at.desc(), Ledger.id).limit(5)).all()
    return render_template("home.html", rows=rows[:3], pos=pos, neg=neg, recent=recent)


@web.route("/people", methods=["GET", "POST"])
@login_required
def contacts():
    if request.method == "POST":
        d = request.form
        name = d.get("name", "").strip()
        if not name or len(name) > 120:
            raise ValueError("A name of up to 120 characters is required.")
        p = Person(
            owner_id=current_user.id,
            name=name,
            phone=phone(d["phone"]) if d.get("phone") else None,
            email=email(d.get("email", "")),
            notes=d.get("notes", "")[:2000],
        )
        db.session.add(p)
        db.session.flush()
        if request.files.get("file") and request.files["file"].filename:
            p.avatar_id = store_upload(current_user, True).id
        r = s.relation(current_user, s.own_person(current_user).id, p.id)
        s.audit(current_user, "contact.create", p)
        db.session.commit()
        return redirect("/relationship/" + r.id)
    rows, _, _ = overview()
    q = request.args.get("q", "").lower()
    rows = [r for r in rows if q in r["name"].lower()]
    return render_template("people.html", rows=rows, partial=bool(request.headers.get("HX-Request")))


@web.get("/relationship/<ident>")
@login_required
def relationship_page(ident):
    r = s.get(Relationship, ident)
    s.require_relation(current_user, r)
    side = s.perspective(current_user, r)
    ps = [s.get(Person, r.left_id), s.get(Person, r.right_id)]
    page = max(1, int(request.args.get("page", 1)))
    entries = db.session.scalars(
        select(Ledger)
        .where(Ledger.relationship_id == ident)
        .order_by(Ledger.date.desc(), Ledger.created_at.desc(), Ledger.id)
        .offset((page - 1) * 40)
        .limit(41)
    ).all()
    reviews = db.session.scalars(
        select(Review).where(Review.ledger_id.in_([e.id for e in entries])).order_by(Review.created_at)
    ).all()
    return render_template(
        "relationship.html",
        r=r,
        ps=ps,
        side=side,
        balance=s.balance(r, side) if side else None,
        entries=entries[:40],
        more=len(entries) > 40,
        page=page,
        reviews=reviews,
    )


@web.get("/add")
@login_required
def add():
    rows, _, _ = overview()
    return render_template("add.html", rows=rows, persons=people(), selected=request.args.get("relationship_id"))


@web.get("/split")
@login_required
def split_page():
    return render_template("expense_form.html", persons=people(), g=None, expense=None)


@web.get("/groups")
@login_required
def groups():
    return render_template(
        "groups.html",
        groups=db.session.scalars(groups_query().order_by(Group.created_at.desc()).limit(100)).all(),
        persons=people(),
    )


@web.get("/group/<ident>")
@login_required
def group_page(ident):
    g = s.get(Group, ident)
    s.require_group(current_user, g)
    members = s.group_members(g)
    ps = {p.id: p for p in db.session.scalars(select(Person).where(Person.id.in_([m.person_id for m in members])))}
    expenses = db.session.scalars(
        select(Expense).where(Expense.group_id == g.id).order_by(Expense.created_at.desc())
    ).all()
    reviews = db.session.scalars(
        select(Review)
        .where(or_(Review.group_id == g.id, Review.expense_id.in_([e.id for e in expenses])))
        .order_by(Review.created_at)
    ).all()
    return render_template(
        "group.html",
        g=g,
        members=members,
        ps=ps,
        state=s.group_state(g),
        expenses=expenses,
        disputes=s.group_disputes(g),
        reviews=reviews,
        persons=people(),
    )


@web.get("/group/<ident>/expense")
@login_required
def expense_page(ident):
    g = s.get(Group, ident)
    s.require_group(current_user, g)
    ps = db.session.scalars(select(Person).where(Person.id.in_([m.person_id for m in s.group_members(g)]))).all()
    e = s.get(Expense, request.args["replace"]) if request.args.get("replace") else None
    if e and e.group_id != g.id:
        raise Forbidden()
    return render_template("expense_form.html", g=g, persons=ps, expense=e)


@web.get("/bill/<ident>")
@login_required
def bill(ident):
    e = s.get(Expense, ident)
    if e.group_id:
        g = s.get(Group, e.group_id)
        s.require_group(current_user, g)
    elif e.owner_id != current_user.id:
        if not db.session.scalar(
            ledger_query().where(Ledger.source == "split", Ledger.source_id == e.id).with_only_columns(Ledger.id)
        ):
            raise Forbidden()
    shares = db.session.execute(
        select(Share, Person).join(Person, Share.person_id == Person.id).where(Share.expense_id == e.id)
    ).all()
    return render_template("bill.html", e=e, shares=shares, payer=s.get(Person, e.payer_id))


@web.post("/action/<action>")
@login_required
def action(action):
    if action not in s.ACTIONS:
        raise ValueError("Unknown action.")
    d = data()
    key = request.headers.get("Idempotency-Key") or d.pop("key", None)
    d.pop("csrf_token", None)
    # Serialize mutations by actor as well as resource, with a consistent lock order.
    actor = s.get(User, current_user.id, True)
    if not actor.active or session.get("sv") != actor.session_version:
        raise Forbidden("Your session has expired. Sign in again.")
    uploaded = request.files.get("file")
    file_digest = None
    if uploaded and uploaded.filename:
        raw = uploaded.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError("Attachments must be at most 8 MiB.")
        file_digest = hashlib.sha256(raw).hexdigest()
        uploaded.seek(0)
    op = s.begin(current_user, key, {"action": action, "data": d, "file": file_digest})
    if op.result:
        result = op.result
    else:
        if request.files.get("file") and request.files["file"].filename:
            d["attachment_id"] = store_upload(current_user).id
        result = s.ACTIONS[action](current_user, op, d)
        op.result = result
    db.session.commit()
    if request.is_json:
        return jsonify(result)
    flash("Saved.")
    return redirect(result.get("path", "/"))


@web.get("/activity")
@login_required
def activity():
    q = ledger_query()
    args = request.args
    if args.get("q"):
        q = q.where(Ledger.description.ilike("%" + args["q"][:100] + "%"))
    for k in ("kind", "source", "relationship_id"):
        if args.get(k):
            q = q.where(getattr(Ledger, k) == args[k])
    if args.get("from"):
        q = q.where(Ledger.date >= s.effective(args["from"]))
    if args.get("to"):
        q = q.where(Ledger.date <= s.effective(args["to"]))
    if args.get("min"):
        q = q.where(func.abs(Ledger.cents) >= s.money(args["min"], True))
    if args.get("max"):
        q = q.where(func.abs(Ledger.cents) <= s.money(args["max"], True))
    page = max(1, int(args.get("page", 1)))
    records = db.session.scalars(
        q.order_by(Ledger.date.desc(), Ledger.created_at.desc(), Ledger.id).offset((page - 1) * 40).limit(41)
    ).all()
    rows, _, _ = overview()
    next_args = args.to_dict()
    next_args["page"] = page + 1
    return render_template(
        "activity.html",
        entries=records[:40],
        rows=rows,
        more=len(records) > 40,
        next_url=url_for("web.activity", **next_args),
    )


@web.get("/search")
@login_required
def search():
    term = request.args.get("q", "").strip()[:100]
    results = []
    if term:
        pat = "%" + term + "%"
        for p in db.session.scalars(
            select(Person)
            .where(
                Person.owner_id == current_user.id,
                or_(Person.name.ilike(pat), Person.notes.ilike(pat), Person.phone.ilike(pat)),
            )
            .limit(30)
        ):
            results.append((p.name, "/people?q=" + p.name))
        for e in db.session.scalars(ledger_query().where(Ledger.description.ilike(pat)).limit(30)):
            results.append((e.description, "/relationship/" + e.relationship_id))
        for g in db.session.scalars(
            groups_query().where(or_(Group.name.ilike(pat), Group.description.ilike(pat))).limit(30)
        ):
            results.append((g.name, "/group/" + g.id))
        allowed_groups = groups_query().with_only_columns(Group.id)
        allowed_bills = ledger_query().where(Ledger.source == "split").with_only_columns(Ledger.source_id)
        for e in db.session.scalars(
            select(Expense)
            .where(
                or_(
                    Expense.owner_id == current_user.id,
                    Expense.group_id.in_(allowed_groups),
                    Expense.id.in_(allowed_bills),
                ),
                Expense.description.ilike(pat),
            )
            .limit(30)
        ):
            results.append((e.description, "/bill/" + e.id))
    return render_template("search.html", results=results)


@web.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        d = request.form
        u = s.get(User, current_user.id, True)
        if not check_password_hash(u.password_hash, d.get("current_password", "")):
            raise ValueError("Current password is required to change your profile.")
        if d.get("deactivate") == "yes":
            u.active = False
            u.session_version += 1
        else:
            name = d.get("name", "").strip()
            if not name or len(name) > 120:
                raise ValueError("Name is required (maximum 120 characters).")
            new_phone = phone(d.get("phone", ""))
            u.email = email(d.get("email", ""))
            u.name = name
            if new_phone != u.phone:
                # Existing accepted financial identity cannot be reassigned by changing a number.
                u.phone = new_phone
                u.verified = False
                u.session_version += 1
            if d.get("password"):
                u.password_hash = password(d["password"])
                u.session_version += 1
            if request.files.get("file") and request.files["file"].filename:
                u.avatar_id = store_upload(u, True).id
            p = s.own_person(u)
            p.name = u.name
            p.phone = u.phone
            p.email = u.email
        s.audit(u, "account.update", u)
        db.session.commit()
        if not u.active:
            logout_user()
            session.clear()
            return redirect("/login")
        session["sv"] = u.session_version
        flash("Profile updated.")
        return redirect("/profile")
    return render_template("profile.html")


@web.get("/invitations")
@login_required
def invitations():
    inv = db.session.scalars(
        select(Invitation)
        .where(or_(Invitation.target_id == current_user.id, Invitation.sender_id == current_user.id))
        .order_by(Invitation.created_at.desc())
        .limit(100)
    ).all()
    senders = dict(db.session.execute(select(User.id, User.name).where(User.id.in_([i.sender_id for i in inv]))).all())
    return render_template("invitations.html", invitations=inv, senders=senders)


@web.route("/notifications", methods=["GET", "POST"])
@login_required
def notifications():
    if request.method == "POST":
        n = s.get(Notification, request.form["id"])
        if n.user_id != current_user.id:
            raise Forbidden()
        n.read = request.form.get("read") == "yes"
        db.session.commit()
        return redirect("/notifications")
    return render_template(
        "notifications.html",
        notifications=db.session.scalars(
            select(Notification)
            .where(Notification.user_id == current_user.id)
            .order_by(Notification.created_at.desc())
            .limit(100)
        ).all(),
    )


@web.get("/api/sync")
@login_required
def sync():
    # Stateless snapshot digest: avoids sequence-ID commit-order races. Polling never advances past an uncommitted event.
    rows = db.session.execute(
        select(Notification.id, Notification.read)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.id)
    ).all()
    digest = hashlib.sha256(repr(rows).encode()).hexdigest()
    return jsonify(
        revision=digest, changed=request.args.get("revision") != digest, unread=sum(not row.read for row in rows)
    )


@web.post("/api/theme")
@login_required
def theme():
    value = request.get_json().get("theme")
    if value not in ("light", "dark", "system"):
        raise ValueError("Invalid theme.")
    current_user.theme = value
    db.session.commit()
    return jsonify(saved=True)


def store_upload(user, images_only=False):
    f = request.files["file"]
    raw = f.read(8 * 1024 * 1024 + 1)
    if not raw or len(raw) > 8 * 1024 * 1024:
        raise ValueError("Attachments must be at most 8 MiB.")
    if raw.startswith(b"%PDF-") and not images_only:
        # Serve PDFs as downloads, never inline in the authenticated origin.
        ext = "pdf"
        mime = "application/pdf"
        if b"%%EOF" not in raw[-1024:]:
            raise ValueError("Invalid PDF.")
    else:
        try:
            Image.MAX_IMAGE_PIXELS = 20_000_000
            im = Image.open(io.BytesIO(raw))
            im.verify()
            im = Image.open(io.BytesIO(raw))
            if im.format not in ("JPEG", "PNG", "WEBP"):
                raise ValueError("Use JPEG, PNG, WebP, or PDF.")
            if im.width * im.height > 20_000_000:
                raise ValueError("Images must be at most 20 megapixels.")
            im.thumbnail((1600, 1600))
            out = io.BytesIO()
            im.convert("RGB").save(out, format="WEBP", quality=85)
            raw = out.getvalue()
            ext = "webp"
            mime = "image/webp"
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            raise ValueError("Invalid image.") from None
    stored = secrets.token_hex(24) + "." + ext
    Path(current_app.config["UPLOAD_FOLDER"], stored).write_bytes(raw)
    a = Attachment(
        owner_id=user.id, filename=Path(f.filename or "attachment").name[:255], stored=stored, mime=mime, size=len(raw)
    )
    db.session.add(a)
    db.session.flush()
    return a


@web.get("/attachment/<ident>")
@login_required
def download(ident):
    a = s.get(Attachment, ident)
    allowed = a.owner_id == current_user.id
    if not allowed:
        allowed = bool(
            db.session.scalar(ledger_query().where(Ledger.attachment_id == ident).with_only_columns(Ledger.id))
        )
        if not allowed:
            allowed = bool(
                db.session.scalar(
                    select(Expense.id).where(
                        Expense.attachment_id == ident,
                        or_(
                            Expense.group_id.in_(groups_query().with_only_columns(Group.id)),
                            Expense.id.in_(
                                ledger_query().where(Ledger.source == "split").with_only_columns(Ledger.source_id)
                            ),
                        ),
                    )
                )
            )
    if not allowed:
        raise Forbidden()
    response = send_file(
        Path(current_app.config["UPLOAD_FOLDER"], a.stored),
        mimetype=a.mime,
        download_name=a.filename,
        as_attachment=a.mime == "application/pdf",
    )
    response.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response


@web.get("/health")
def health():
    db.session.execute(select(1))
    return jsonify(status="ok")


@web.get("/sw.js")
def sw():
    response = current_app.send_static_file("sw.js")
    response.headers["Service-Worker-Allowed"] = "/"
    return response
