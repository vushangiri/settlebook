"""Transaction-scoped services. Caller commits once, including notifications and audit."""

import hashlib
import json
from datetime import date, timedelta
from sqlalchemy import select, func, or_
from sqlalchemy.dialects.postgresql import insert
from werkzeug.exceptions import Forbidden, NotFound, Conflict
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
    Snapshot,
    Transfer,
    Invitation,
    Attachment,
    Notification,
    Audit,
    Operation,
)
from .accounting import money, split, net, settle


def get(model, ident, lock=False):
    stmt = select(model).where(model.id == ident)
    if lock:
        stmt = stmt.with_for_update(key_share=True).execution_options(populate_existing=True)
    obj = db.session.scalar(stmt)
    if obj is None:
        raise NotFound()
    return obj


def audit(user, action, target, data=None):
    db.session.add(Audit(actor_id=user.id, action=action, target_id=target.id, data=data or {}))


def notify(ids, message, path):
    for ident in set(ids):
        db.session.add(Notification(user_id=ident, message=message, path=path))


def own_person(user):
    return db.session.scalar(select(Person).where(Person.owner_id == user.id, Person.is_self.is_(True)))


def own(user, person_id):
    p = get(Person, person_id)
    if p.owner_id != user.id:
        raise Forbidden()
    return p


def identity_map(person_ids):
    """Resolve accepted aliases in three batched queries, never by phone matching."""
    ids = set(person_ids)
    persons = db.session.scalars(select(Person).where(Person.id.in_(ids))).all()
    accounts = {p.id: set() for p in persons}
    for pid, uid in db.session.execute(select(Access.person_id, Access.user_id).where(Access.person_id.in_(ids))):
        accounts[pid].add(uid)
    for pid, uid in db.session.execute(
        select(Member.person_id, Member.user_id).where(
            Member.person_id.in_(ids), Member.accepted.is_(True), Member.user_id.is_not(None)
        )
    ):
        accounts[pid].add(uid)
    return {
        p.id: ("user", p.owner_id)
        if p.is_self
        else ("user", next(iter(accounts[p.id])))
        if len(accounts[p.id]) == 1
        else ("person", p.id)
        for p in persons
    }


def identity(person_id):
    return identity_map([person_id])[person_id]


def selectable_people(user):
    shared = db.session.scalars(
        select(Relationship).where(Relationship.id.in_(select(Access.relationship_id).where(Access.user_id == user.id)))
    ).all()
    ids = {pid for r in shared for pid in (r.left_id, r.right_id)}
    candidates = db.session.scalars(
        select(Person)
        .where(or_(Person.owner_id == user.id, Person.id.in_(ids)))
        .order_by(Person.is_self.desc(), Person.name, Person.id)
    ).all()
    result = {}
    me = own_person(user)
    result[("user", user.id)] = me
    identities = identity_map([p.id for p in candidates])
    for p in candidates:
        result.setdefault(identities[p.id], p)
    return list(result.values())


def selectable(user, person_id):
    if person_id not in {p.id for p in selectable_people(user)}:
        raise Forbidden()
    return get(Person, person_id)


def relation_side(r, person_id):
    if person_id in (r.left_id, r.right_id):
        return person_id
    ident = identity(person_id)
    for candidate in (r.left_id, r.right_id):
        if identity(candidate) == ident:
            return candidate
    raise ValueError("Participant is not part of this relationship.")


def relation(user, a, b, owner_id=None):
    pair = {identity(a), identity(b)}
    if len(pair) != 2:
        raise ValueError("Self obligations are not allowed.")
    # Reuse an already-authorized shared relationship across local contact aliases.
    candidates = db.session.scalars(
        select(Relationship)
        .where(
            or_(
                Relationship.owner_id == user.id,
                Relationship.id.in_(select(Access.relationship_id).where(Access.user_id == user.id)),
            )
        )
        .order_by(Relationship.created_at, Relationship.id)
    ).all()
    identities = identity_map([p for r in candidates for p in (r.left_id, r.right_id)])
    for existing in candidates:
        if {identities[existing.left_id], identities[existing.right_id]} == pair:
            return get(Relationship, existing.id, True)
    left, right = sorted((a, b))
    owner_id = owner_id or user.id
    # Same pair is locked by the unique index, including simultaneous first posts.
    db.session.execute(
        insert(Relationship)
        .values(owner_id=owner_id, left_id=left, right_id=right, currency="AUD")
        .on_conflict_do_nothing(index_elements=["left_id", "right_id", "currency"])
    )
    r = db.session.scalar(
        select(Relationship)
        .where(Relationship.left_id == left, Relationship.right_id == right, Relationship.currency == "AUD")
        .with_for_update()
    )
    return r


def can_relation(user, r):
    return (
        r.owner_id == user.id
        or db.session.scalar(select(Access.id).where(Access.relationship_id == r.id, Access.user_id == user.id))
        is not None
    )


def require_relation(user, r):
    if not can_relation(user, r):
        raise Forbidden()


def perspective(user, r):
    access = db.session.scalar(select(Access).where(Access.relationship_id == r.id, Access.user_id == user.id))
    if access:
        return access.person_id
    p = own_person(user)
    return p.id if p.id in (r.left_id, r.right_id) else None


def balance(r, person_id):
    total = db.session.scalar(select(func.coalesce(func.sum(Ledger.cents), 0)).where(Ledger.relationship_id == r.id))
    return int(total) * (1 if person_id == r.left_id else -1)


def recipients(r):
    return [r.owner_id, *db.session.scalars(select(Access.user_id).where(Access.relationship_id == r.id)).all()]


def attachment(user, ident):
    if ident and get(Attachment, ident).owner_id != user.id:
        raise Forbidden()
    return ident or None


def effective(value):
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError("Supply a valid transaction date.") from None


def begin(user, key, payload):
    if not key or not 8 <= len(key) <= 128:
        raise ValueError("An idempotency key of 8–128 characters is required.")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    db.session.execute(
        insert(Operation)
        .values(actor_id=user.id, key=key, fingerprint=digest)
        .on_conflict_do_nothing(index_elements=["actor_id", "key"])
    )
    op = db.session.scalar(
        select(Operation).where(Operation.actor_id == user.id, Operation.key == key).with_for_update()
    )
    if op.fingerprint != digest:
        raise Conflict("This submission key was already used for different data.")
    return op


def post(
    user,
    op,
    r,
    creditor_id,
    cents,
    kind,
    description,
    when,
    source="personal",
    source_id=None,
    attachment_id=None,
    reversal_of=None,
    repayment_of=None,
):
    creditor_id = relation_side(r, creditor_id)
    if type(cents) is not int or cents <= 0:
        raise ValueError("Invalid obligation.")
    e = Ledger(
        relationship_id=r.id,
        actor_id=user.id,
        cents=cents if creditor_id == r.left_id else -cents,
        kind=kind,
        description=description[:500],
        date=effective(when),
        source=source,
        source_id=source_id,
        attachment_id=attachment(user, attachment_id),
        operation_id=op.id,
        reversal_of=reversal_of,
        repayment_of=repayment_of,
    )
    db.session.add(e)
    db.session.flush()
    audit(user, "ledger.post", e, {"kind": kind, "source": source, "source_id": source_id})
    notify(recipients(r), "Ledger updated: " + description[:150], "/relationship/" + r.id)
    return e


def entry(user, op, data):
    r = get(Relationship, data["relationship_id"], True)
    require_relation(user, r)
    me = perspective(user, r)
    if me is None:
        if r.owner_id != user.id or data.get("perspective_id") not in (r.left_id, r.right_id):
            raise ValueError("Choose the participant whose perspective is being recorded.")
        me = data["perspective_id"]
    other = r.right_id if me == r.left_id else r.left_id
    kind = data["kind"]
    n = money(data["amount"])
    if kind not in ("given", "taken", "repayment_received", "repayment_made", "adjustment"):
        raise ValueError("Invalid entry type.")
    if kind.startswith("repayment"):
        b = balance(r, me)
        if (kind == "repayment_received" and b <= 0) or (kind == "repayment_made" and b >= 0) or n > abs(b):
            raise ValueError("Repayment must match the debt direction and cannot exceed the balance.")
    reference = data.get("repayment_of") or None
    if reference:
        original = get(Ledger, reference)
        if not kind.startswith("repayment") or original.relationship_id != r.id:
            raise ValueError("A repayment reference must belong to this ledger.")
    creditor = me if kind in ("given", "repayment_made") else other
    if kind == "adjustment":
        creditor = data.get("creditor_id")
        if not data.get("description"):
            raise ValueError("An adjustment reason is required.")
    e = post(
        user,
        op,
        r,
        creditor,
        n,
        kind,
        data.get("description", "") or kind.replace("_", " "),
        data["date"],
        attachment_id=data.get("attachment_id"),
        repayment_of=reference,
    )
    return {"id": e.id, "path": "/relationship/" + r.id}


def reverse(user, op, data):
    e = get(Ledger, data["entry_id"])
    r = get(Relationship, e.relationship_id, True)
    require_relation(user, r)
    if e.actor_id != user.id and r.owner_id != user.id:
        raise Forbidden()
    if not data.get("description"):
        raise ValueError("A correction reason is required.")
    if db.session.scalar(select(Ledger.id).where(Ledger.reversal_of == e.id)):
        raise Conflict("Already reversed.")
    creditor = r.right_id if e.cents > 0 else r.left_id
    result = post(
        user,
        op,
        r,
        creditor,
        abs(e.cents),
        "reversal",
        data["description"],
        data["date"],
        "correction",
        e.id,
        reversal_of=e.id,
    )
    return {"id": result.id, "path": "/relationship/" + r.id}


def can_group(user, g):
    return (
        g.owner_id == user.id
        or db.session.scalar(
            select(Member.id).where(Member.group_id == g.id, Member.user_id == user.id, Member.accepted.is_(True))
        )
        is not None
    )


def require_group(user, g, admin=False):
    if not can_group(user, g) or (admin and g.owner_id != user.id):
        raise Forbidden()


def group_members(g):
    return db.session.scalars(select(Member).where(Member.group_id == g.id).order_by(Member.person_id)).all()


def new_group(user, op, data):
    ids = list(dict.fromkeys([own_person(user).id, *data.get("participants", [])]))
    if not 2 <= len(ids) <= 200:
        raise ValueError("Groups require between 2 and 200 members.")
    for ident in ids:
        selectable(user, ident)
    if not data.get("name", "").strip():
        raise ValueError("Group name is required.")
    g = Group(owner_id=user.id, name=data["name"][:120], description=data.get("description", "")[:2000])
    db.session.add(g)
    db.session.flush()
    for ident in ids:
        db.session.add(
            Member(
                group_id=g.id,
                person_id=ident,
                user_id=user.id if ident == own_person(user).id else None,
                accepted=ident == own_person(user).id,
            )
        )
    audit(user, "group.create", g)
    return {"id": g.id, "path": "/group/" + g.id}


def add_member(user, op, data):
    g = get(Group, data["group_id"], True)
    require_group(user, g, True)
    if g.status != "open":
        raise Conflict("Members can only be added to an open group.")
    if len(group_members(g)) >= 200:
        raise ValueError("Groups support up to 200 members.")
    p = selectable(user, data["person_id"])
    if db.session.scalar(select(Member.id).where(Member.group_id == g.id, Member.person_id == p.id)):
        raise Conflict("Already a member.")
    db.session.add(Member(group_id=g.id, person_id=p.id))
    g.revision += 1
    audit(user, "group.member.add", g, {"person_id": p.id})
    return {"path": "/group/" + g.id}


def make_expense(user, op, data):
    gid = data.get("group_id")
    g = get(Group, gid, True) if gid else None
    payer = data["payer_id"]
    participants = data.get("participants", [])
    if not 1 <= len(participants) <= 200:
        raise ValueError("Select between 1 and 200 participants.")
    if g:
        require_group(user, g)
        if g.status != "open":
            raise Conflict("Expenses can only be changed while the group is open.")
        allowed = {m.person_id for m in group_members(g)}
    else:
        allowed = {p.id for p in selectable_people(user)}
    if payer not in allowed or set(participants) - allowed:
        raise Forbidden()
    if len({identity(p) for p in participants}) != len(participants):
        raise ValueError("The same account cannot participate twice through different contacts.")
    n = money(data["amount"])
    method = data.get("method", "equal")
    custom = {p: money(data.get("shares", {}).get(p, ""), True) for p in participants} if method == "custom" else None
    shares = split(n, participants, method, custom)
    replaces = data.get("replaces_id")
    if replaces:
        if not g:
            raise ValueError("Posted split bills require ledger reversals or adjustments.")
        require_group(user, g, True)
        old = get(Expense, replaces, True)
        if old.group_id != g.id or not old.active:
            raise Conflict("Expense is not an active expense in this group.")
        if unresolved(expense_id=old.id):
            raise Conflict("Resolve the expense dispute before replacing it.")
        old.active = False
        audit(user, "expense.supersede", old, {"reason": data.get("description", "")})
    e = Expense(
        owner_id=user.id,
        group_id=gid,
        payer_id=payer,
        description=data.get("description", "")[:500] or "Shared expense",
        notes=data.get("notes", "")[:2000],
        cents=n,
        method=method,
        date=effective(data["date"]),
        attachment_id=attachment(user, data.get("attachment_id")),
        operation_id=op.id,
        replaces_id=replaces,
    )
    db.session.add(e)
    db.session.flush()
    for p, amount in shares.items():
        db.session.add(Share(expense_id=e.id, person_id=p, cents=amount))
    if g:
        g.revision += 1
        notify(
            [m.user_id for m in group_members(g) if m.accepted and m.user_id],
            "Group expense: " + e.description[:150],
            "/group/" + g.id,
        )
    else:
        for p, amount in sorted(shares.items()):
            if identity(p) != identity(payer) and amount:
                r = relation(user, payer, p)
                post(user, op, r, payer, amount, "split", e.description, data["date"], "split", e.id)
    audit(user, "expense.create", e)
    return {"id": e.id, "path": "/group/" + g.id if g else "/bill/" + e.id}


def group_state(g):
    members = group_members(g)
    expenses = db.session.scalars(
        select(Expense).where(Expense.group_id == g.id, Expense.active.is_(True)).order_by(Expense.id)
    ).all()
    ids = [e.id for e in expenses]
    allocations = {eid: {} for eid in ids}
    for s in db.session.scalars(select(Share).where(Share.expense_id.in_(ids))):
        allocations[s.expense_id][s.person_id] = s.cents
    balances = net([(e.payer_id, e.cents, allocations[e.id]) for e in expenses], [m.person_id for m in members])
    paid = {m.person_id: 0 for m in members}
    owed = dict(paid)
    for expense in expenses:
        paid[expense.payer_id] += expense.cents
        for pid, amount in allocations[expense.id].items():
            owed[pid] += amount
    return {
        "paid": paid,
        "owed": owed,
        "revision": g.revision,
        "total": sum(e.cents for e in expenses),
        "net": balances,
        "expenses": [
            {"id": e.id, "payer": e.payer_id, "total": e.cents, "shares": allocations[e.id]} for e in expenses
        ],
        "transfers": settle(balances),
    }


def unresolved(**filters):
    resolved = select(Review.resolves_id).where(Review.resolves_id.is_not(None))
    stmt = select(Review).where(Review.status == "disputed", Review.id.not_in(resolved))
    for key, value in filters.items():
        stmt = stmt.where(getattr(Review, key) == value)
    return db.session.scalars(stmt).all()


def group_disputes(g):
    ids = select(Expense.id).where(Expense.group_id == g.id)
    resolved = select(Review.resolves_id).where(Review.resolves_id.is_not(None))
    return db.session.scalars(
        select(Review).where(
            or_(Review.group_id == g.id, Review.expense_id.in_(ids)),
            Review.status == "disputed",
            Review.id.not_in(resolved),
        )
    ).all()


def group_status(user, op, data):
    g = get(Group, data["group_id"], True)
    require_group(user, g, True)
    target = data["status"]
    if (g.status, target) not in (("open", "review"), ("review", "open"), ("finalized", "archived")):
        raise Conflict("Invalid state transition.")
    g.status = target
    g.revision += 1
    audit(user, "group." + target, g)
    notify(
        [m.user_id for m in group_members(g) if m.accepted and m.user_id], "Group status: " + target, "/group/" + g.id
    )
    return {"path": "/group/" + g.id}


def finalize(user, op, data):
    g = get(Group, data["group_id"], True)
    require_group(user, g, True)
    existing = db.session.scalar(select(Snapshot).where(Snapshot.group_id == g.id))
    if existing:
        return {"id": existing.id, "path": "/group/" + g.id}
    if g.status != "review":
        raise Conflict("Put the group under review first.")
    if int(data.get("revision", -1)) != g.revision:
        raise Conflict("The group changed. Review the new settlement before confirming.")
    if data.get("confirm") != "yes":
        raise ValueError("Explicit confirmation is required.")
    if group_disputes(g):
        raise Conflict("Resolve all disputes before finalizing.")
    state = group_state(g)
    snap = Snapshot(group_id=g.id, revision=g.revision, data=state)
    db.session.add(snap)
    db.session.flush()
    members = {m.person_id: m for m in group_members(g)}
    # Canonical pair order avoids opposing lock acquisition across groups.
    for debtor, creditor, amount in sorted(state["transfers"], key=lambda t: tuple(sorted(t[:2]))):
        r = relation(user, debtor, creditor, g.owner_id)
        for p in (debtor, creditor):
            m = members[p]
            if m.user_id and m.accepted:
                db.session.execute(
                    insert(Access)
                    .values(relationship_id=r.id, user_id=m.user_id, person_id=relation_side(r, p))
                    .on_conflict_do_nothing(index_elements=["relationship_id", "user_id"])
                )
        e = post(
            user,
            op,
            r,
            creditor,
            amount,
            "group",
            "Group settlement: " + g.name,
            date.today().isoformat(),
            "group",
            g.id,
        )
        db.session.add(
            Transfer(snapshot_id=snap.id, debtor_id=debtor, creditor_id=creditor, cents=amount, ledger_id=e.id)
        )
    g.status = "finalized"
    g.revision += 1
    audit(user, "group.finalize", g, state)
    notify(
        [m.user_id for m in members.values() if m.user_id and m.accepted],
        "Group finalized; obligations recorded, no money transferred.",
        "/group/" + g.id,
    )
    return {"id": snap.id, "path": "/group/" + g.id}


def invite(user, op, data):
    p = selectable(user, data["person_id"])
    target = db.session.scalar(
        select(User).where(User.phone == p.phone, User.verified.is_(True), User.active.is_(True))
    )
    if not target or target.id == user.id:
        raise ValueError("No eligible verified account. Verify the phone with the administrator first.")
    rid, mid = data.get("relationship_id"), data.get("member_id")
    if bool(rid) == bool(mid):
        raise ValueError("Choose exactly one sharing scope.")
    if rid:
        r = get(Relationship, rid, True)
        if r.owner_id != user.id or p.id not in (r.left_id, r.right_id):
            raise Forbidden()
        if db.session.scalar(select(Access.id).where(Access.relationship_id == r.id, Access.person_id == p.id)):
            raise Conflict("This ledger participant is already linked to an account.")
    else:
        m = get(Member, mid)
        g = get(Group, m.group_id, True)
        require_group(user, g, True)
        if m.person_id != p.id or g.status not in ("open", "review"):
            raise Forbidden()
        if m.accepted:
            raise Conflict("Membership is already accepted.")
    inv = Invitation(
        sender_id=user.id,
        target_id=target.id,
        person_id=p.id,
        relationship_id=rid,
        member_id=mid,
        expires_at=now() + timedelta(days=7),
    )
    db.session.add(inv)
    db.session.flush()
    audit(user, "invitation.create", inv)
    notify(
        [target.id], "Invitation to share a ledger or group. Acceptance reveals its existing history.", "/invitations"
    )
    return {"id": inv.id, "path": "/invitations"}


def accept_invite(user, op, data):
    inv = get(Invitation, data["invitation_id"], True)
    if inv.target_id != user.id:
        raise Forbidden()
    if inv.status != "pending" or inv.expires_at < now():
        raise Conflict("Invitation has expired or was already answered.")
    if not user.verified:
        raise Forbidden("Phone verification is required before accepting.")
    inv.status = "accepted" if data.get("accept") == "yes" else "declined"
    if inv.status == "accepted":
        if inv.relationship_id:
            r = get(Relationship, inv.relationship_id, True)
            existing = db.session.scalar(
                select(Access).where(Access.relationship_id == r.id, Access.person_id == inv.person_id)
            )
            if existing and existing.user_id != user.id:
                raise Conflict("This participant is already linked to another account.")
            db.session.execute(
                insert(Access)
                .values(relationship_id=r.id, user_id=user.id, person_id=inv.person_id)
                .on_conflict_do_nothing(index_elements=["relationship_id", "user_id"])
            )
        else:
            m = get(Member, inv.member_id)
            g = get(Group, m.group_id, True)
            if g.status not in ("open", "review"):
                raise Conflict("Group sharing is frozen after finalization.")
            if m.accepted and m.user_id != user.id:
                raise Conflict("This membership is already linked to another account.")
            m.user_id = user.id
            m.accepted = True
            g.revision += 1
    audit(user, "invitation." + inv.status, inv)
    notify([inv.sender_id], "Invitation " + inv.status, "/invitations")
    return {"path": "/"}


def review(user, op, data):
    lid, eid, gid = data.get("ledger_id"), data.get("expense_id"), data.get("group_id")
    if sum(bool(v) for v in (lid, eid, gid)) != 1:
        raise ValueError("Select one review target.")
    if lid:
        e = get(Ledger, lid)
        r = get(Relationship, e.relationship_id, True)
        require_relation(user, r)
        ids = recipients(r)
        path = "/relationship/" + r.id
    else:
        if eid:
            e = get(Expense, eid)
            if not e.group_id:
                raise ValueError("Review the posted split obligation in its ledger.")
            gid = e.group_id
        g = get(Group, gid, True)
        require_group(user, g)
        ids = [m.user_id for m in group_members(g) if m.user_id and m.accepted]
        path = "/group/" + g.id
    status = data["status"]
    if status not in ("acknowledged", "disputed", "resolved"):
        raise ValueError("Invalid review status.")
    if not data.get("note"):
        raise ValueError("Supply a review note.")
    resolves = data.get("resolves_id") or None
    if status == "resolved":
        original = get(Review, resolves)
        if original.user_id != user.id or original.status != "disputed":
            raise Forbidden("Only the disputing user can resolve their dispute.")
        if (original.ledger_id, original.expense_id, original.group_id) != (
            lid or None,
            eid or None,
            None if eid else gid or None,
        ):
            raise ValueError("Resolution target mismatch.")
    elif resolves:
        raise ValueError("Only resolutions may reference a dispute.")
    rev = Review(
        user_id=user.id,
        ledger_id=lid or None,
        expense_id=eid or None,
        group_id=None if eid else gid or None,
        status=status,
        note=data["note"][:1000],
        resolves_id=resolves,
    )
    db.session.add(rev)
    db.session.flush()
    audit(user, "review." + status, rev)
    notify(ids, "Review: " + status, path)
    return {"path": path}


ACTIONS = {
    "entry": entry,
    "reverse": reverse,
    "expense": make_expense,
    "group": new_group,
    "member": add_member,
    "group-status": group_status,
    "finalize": finalize,
    "invite": invite,
    "accept": accept_invite,
    "review": review,
}
