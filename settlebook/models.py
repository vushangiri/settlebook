"""PostgreSQL is the only supported database. Amounts are signed BIGINT cents."""

import uuid
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy import event

db = SQLAlchemy()


def uid():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc)


def fk(table, **kw):
    return db.Column(db.String(36), db.ForeignKey(table + ".id", ondelete="RESTRICT"), **kw)


class Base(db.Model):
    __abstract__ = True
    id = db.Column(db.String(36), primary_key=True, default=uid)
    created_at = db.Column(db.DateTime(timezone=True), default=now, nullable=False)


class User(UserMixin, Base):
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(254), unique=True)
    password_hash = db.Column(db.Text, nullable=False)
    verified = db.Column(db.Boolean, default=False, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    session_version = db.Column(db.Integer, default=1, nullable=False)
    theme = db.Column(db.String(10), default="system", nullable=False)
    avatar_id = db.Column(db.String(36))

    @property
    def is_active(self):
        return self.active


class Person(Base):
    owner_id = fk("user", nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), index=True)
    email = db.Column(db.String(254))
    notes = db.Column(db.Text, default="")
    avatar_id = db.Column(db.String(36))
    is_self = db.Column(db.Boolean, default=False, nullable=False)
    __table_args__ = (db.Index("one_self_per_owner", "owner_id", unique=True, postgresql_where=db.text("is_self")),)


class Relationship(Base):
    owner_id = fk("user", nullable=False, index=True)
    left_id = fk("person", nullable=False)
    right_id = fk("person", nullable=False)
    currency = db.Column(db.String(3), default="AUD", nullable=False)
    __table_args__ = (db.UniqueConstraint("left_id", "right_id", "currency"), db.CheckConstraint("left_id < right_id"))


class Access(Base):
    relationship_id = fk("relationship", nullable=False, index=True)
    user_id = fk("user", nullable=False, index=True)
    person_id = fk("person", nullable=False)
    __table_args__ = (
        db.UniqueConstraint("relationship_id", "user_id"),
        db.UniqueConstraint("relationship_id", "person_id"),
    )


class Ledger(Base):
    relationship_id = fk("relationship", nullable=False, index=True)
    actor_id = fk("user", nullable=False)
    cents = db.Column(db.BigInteger, nullable=False)  # positive: right owes left
    kind = db.Column(db.String(32), nullable=False, index=True)
    description = db.Column(db.String(500), nullable=False)
    date = db.Column(db.Date, nullable=False, index=True)
    source = db.Column(db.String(20), nullable=False, index=True)
    source_id = db.Column(db.String(36), index=True)
    reversal_of = fk("ledger", unique=True)
    repayment_of = fk("ledger")
    attachment_id = fk("attachment")
    operation_id = fk("operation", nullable=False, index=True)
    __table_args__ = (db.CheckConstraint("cents != 0 AND cents BETWEEN -100000000000 AND 100000000000"),)


class Group(Base):
    owner_id = fk("user", nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, default="")
    status = db.Column(db.String(20), default="open", nullable=False)
    currency = db.Column(db.String(3), default="AUD", nullable=False)
    revision = db.Column(db.Integer, default=1, nullable=False)
    __table_args__ = (db.CheckConstraint("status IN ('open','review','finalized','archived')"),)


class Member(Base):
    group_id = fk("group", nullable=False, index=True)
    person_id = fk("person", nullable=False)
    user_id = fk("user", index=True)
    accepted = db.Column(db.Boolean, default=False, nullable=False)
    __table_args__ = (db.UniqueConstraint("group_id", "person_id"), db.UniqueConstraint("group_id", "user_id"))


class Expense(Base):
    owner_id = fk("user", nullable=False, index=True)
    group_id = fk("group", index=True)
    payer_id = fk("person", nullable=False)
    description = db.Column(db.String(500), nullable=False)
    notes = db.Column(db.Text, default="")
    cents = db.Column(db.BigInteger, nullable=False)
    currency = db.Column(db.String(3), default="AUD", nullable=False)
    method = db.Column(db.String(10), nullable=False)
    date = db.Column(db.Date, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    replaces_id = fk("expense", unique=True)
    attachment_id = fk("attachment")
    operation_id = fk("operation", nullable=False)
    __table_args__ = (db.CheckConstraint("cents > 0 AND cents <= 100000000000"),)


class Share(Base):
    expense_id = fk("expense", nullable=False, index=True)
    person_id = fk("person", nullable=False)
    cents = db.Column(db.BigInteger, nullable=False)
    __table_args__ = (db.UniqueConstraint("expense_id", "person_id"), db.CheckConstraint("cents >= 0"))


class Review(Base):
    user_id = fk("user", nullable=False)
    ledger_id = fk("ledger", index=True)
    expense_id = fk("expense", index=True)
    group_id = fk("group", index=True)
    status = db.Column(db.String(15), nullable=False)
    note = db.Column(db.String(1000), nullable=False)
    resolves_id = fk("review", unique=True)
    __table_args__ = (
        db.CheckConstraint("status IN ('acknowledged','disputed','resolved')"),
        db.CheckConstraint(
            "(CASE WHEN ledger_id IS NULL THEN 0 ELSE 1 END + CASE WHEN expense_id IS NULL THEN 0 ELSE 1 END + CASE WHEN group_id IS NULL THEN 0 ELSE 1 END) = 1"
        ),
    )


class Snapshot(Base):
    group_id = fk("group", nullable=False, unique=True)
    revision = db.Column(db.Integer, nullable=False)
    data = db.Column(db.JSON, nullable=False)


class Transfer(Base):
    snapshot_id = fk("snapshot", nullable=False, index=True)
    debtor_id = fk("person", nullable=False)
    creditor_id = fk("person", nullable=False)
    cents = db.Column(db.BigInteger, nullable=False)
    ledger_id = fk("ledger", nullable=False, unique=True)
    __table_args__ = (db.CheckConstraint("cents > 0"),)


class Invitation(Base):
    sender_id = fk("user", nullable=False)
    target_id = fk("user", index=True)
    target_phone = db.Column(db.String(20), index=True)
    relationship_id = fk("relationship")
    member_id = fk("member")
    person_id = fk("person", nullable=False)
    status = db.Column(db.String(15), default="pending", nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    __table_args__ = (db.CheckConstraint("(relationship_id IS NULL) != (member_id IS NULL)"),)


class Attachment(Base):
    owner_id = fk("user", nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    stored = db.Column(db.String(80), unique=True, nullable=False)
    mime = db.Column(db.String(80), nullable=False)
    size = db.Column(db.Integer, nullable=False)


class Notification(Base):
    user_id = fk("user", nullable=False, index=True)
    message = db.Column(db.String(500), nullable=False)
    path = db.Column(db.String(200), nullable=False)
    read = db.Column(db.Boolean, default=False, nullable=False)


class Audit(Base):
    actor_id = fk("user", nullable=False, index=True)
    action = db.Column(db.String(50), nullable=False)
    target_id = db.Column(db.String(36), nullable=False)
    data = db.Column(db.JSON, nullable=False, default=dict)


class Operation(Base):
    actor_id = fk("user", nullable=False)
    key = db.Column(db.String(128), nullable=False)
    fingerprint = db.Column(db.String(64), nullable=False)
    result = db.Column(db.JSON)
    __table_args__ = (db.UniqueConstraint("actor_id", "key"),)


class ResetToken(Base):
    user_id = fk("user", nullable=False)
    digest = db.Column(db.String(64), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used = db.Column(db.Boolean, default=False, nullable=False)


class RateBucket(db.Model):
    key = db.Column(db.String(64), primary_key=True)
    starts = db.Column(db.DateTime(timezone=True), nullable=False)
    count = db.Column(db.Integer, nullable=False)


for model in (Ledger, Share, Snapshot, Transfer, Audit, Review):

    def deny(mapper, connection, target):
        raise ValueError("Posted records are immutable; use a compensating event.")

    event.listen(model, "before_update", deny)
    event.listen(model, "before_delete", deny)
