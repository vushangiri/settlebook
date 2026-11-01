BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE rate_bucket (
    key VARCHAR(64) NOT NULL, 
    starts TIMESTAMP WITH TIME ZONE NOT NULL, 
    count INTEGER NOT NULL, 
    PRIMARY KEY (key)
);

CREATE TABLE "user" (
    name VARCHAR(120) NOT NULL, 
    phone VARCHAR(20) NOT NULL, 
    email VARCHAR(254), 
    password_hash TEXT NOT NULL, 
    verified BOOLEAN NOT NULL, 
    active BOOLEAN NOT NULL, 
    session_version INTEGER NOT NULL, 
    theme VARCHAR(10) NOT NULL, 
    avatar_id VARCHAR(36), 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (email), 
    UNIQUE (phone)
);

CREATE TABLE attachment (
    owner_id VARCHAR(36) NOT NULL, 
    filename VARCHAR(255) NOT NULL, 
    stored VARCHAR(80) NOT NULL, 
    mime VARCHAR(80) NOT NULL, 
    size INTEGER NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(owner_id) REFERENCES "user" (id) ON DELETE RESTRICT, 
    UNIQUE (stored)
);

CREATE TABLE audit (
    actor_id VARCHAR(36) NOT NULL, 
    action VARCHAR(50) NOT NULL, 
    target_id VARCHAR(36) NOT NULL, 
    data JSON NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(actor_id) REFERENCES "user" (id) ON DELETE RESTRICT
);

CREATE INDEX ix_audit_actor_id ON audit (actor_id);

CREATE TABLE "group" (
    owner_id VARCHAR(36) NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    description TEXT, 
    status VARCHAR(20) NOT NULL, 
    currency VARCHAR(3) NOT NULL, 
    revision INTEGER NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (status IN ('open','review','finalized','archived')), 
    FOREIGN KEY(owner_id) REFERENCES "user" (id) ON DELETE RESTRICT
);

CREATE INDEX ix_group_owner_id ON "group" (owner_id);

CREATE TABLE notification (
    user_id VARCHAR(36) NOT NULL, 
    message VARCHAR(500) NOT NULL, 
    path VARCHAR(200) NOT NULL, 
    read BOOLEAN NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES "user" (id) ON DELETE RESTRICT
);

CREATE INDEX ix_notification_user_id ON notification (user_id);

CREATE TABLE operation (
    actor_id VARCHAR(36) NOT NULL, 
    key VARCHAR(128) NOT NULL, 
    fingerprint VARCHAR(64) NOT NULL, 
    result JSON, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(actor_id) REFERENCES "user" (id) ON DELETE RESTRICT, 
    UNIQUE (actor_id, key)
);

CREATE TABLE person (
    owner_id VARCHAR(36) NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    phone VARCHAR(20), 
    email VARCHAR(254), 
    notes TEXT, 
    avatar_id VARCHAR(36), 
    is_self BOOLEAN NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(owner_id) REFERENCES "user" (id) ON DELETE RESTRICT
);

CREATE INDEX ix_person_owner_id ON person (owner_id);

CREATE UNIQUE INDEX one_self_per_owner ON person (owner_id) WHERE is_self;

CREATE INDEX ix_person_phone ON person (phone);

CREATE TABLE reset_token (
    user_id VARCHAR(36) NOT NULL, 
    digest VARCHAR(64) NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    used BOOLEAN NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES "user" (id) ON DELETE RESTRICT, 
    UNIQUE (digest)
);

CREATE TABLE expense (
    owner_id VARCHAR(36) NOT NULL, 
    group_id VARCHAR(36), 
    payer_id VARCHAR(36) NOT NULL, 
    description VARCHAR(500) NOT NULL, 
    notes TEXT, 
    cents BIGINT NOT NULL, 
    currency VARCHAR(3) NOT NULL, 
    method VARCHAR(10) NOT NULL, 
    date DATE NOT NULL, 
    active BOOLEAN NOT NULL, 
    replaces_id VARCHAR(36), 
    attachment_id VARCHAR(36), 
    operation_id VARCHAR(36) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (cents > 0 AND cents <= 100000000000), 
    FOREIGN KEY(attachment_id) REFERENCES attachment (id) ON DELETE RESTRICT, 
    FOREIGN KEY(group_id) REFERENCES "group" (id) ON DELETE RESTRICT, 
    FOREIGN KEY(operation_id) REFERENCES operation (id) ON DELETE RESTRICT, 
    FOREIGN KEY(owner_id) REFERENCES "user" (id) ON DELETE RESTRICT, 
    FOREIGN KEY(payer_id) REFERENCES person (id) ON DELETE RESTRICT, 
    FOREIGN KEY(replaces_id) REFERENCES expense (id) ON DELETE RESTRICT, 
    UNIQUE (replaces_id)
);

CREATE INDEX ix_expense_owner_id ON expense (owner_id);

CREATE INDEX ix_expense_group_id ON expense (group_id);

CREATE TABLE member (
    group_id VARCHAR(36) NOT NULL, 
    person_id VARCHAR(36) NOT NULL, 
    user_id VARCHAR(36), 
    accepted BOOLEAN NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(group_id) REFERENCES "group" (id) ON DELETE RESTRICT, 
    FOREIGN KEY(person_id) REFERENCES person (id) ON DELETE RESTRICT, 
    FOREIGN KEY(user_id) REFERENCES "user" (id) ON DELETE RESTRICT, 
    UNIQUE (group_id, person_id), 
    UNIQUE (group_id, user_id)
);

CREATE INDEX ix_member_group_id ON member (group_id);

CREATE INDEX ix_member_user_id ON member (user_id);

CREATE TABLE relationship (
    owner_id VARCHAR(36) NOT NULL, 
    left_id VARCHAR(36) NOT NULL, 
    right_id VARCHAR(36) NOT NULL, 
    currency VARCHAR(3) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (left_id < right_id), 
    FOREIGN KEY(left_id) REFERENCES person (id) ON DELETE RESTRICT, 
    FOREIGN KEY(owner_id) REFERENCES "user" (id) ON DELETE RESTRICT, 
    FOREIGN KEY(right_id) REFERENCES person (id) ON DELETE RESTRICT, 
    UNIQUE (left_id, right_id, currency)
);

CREATE INDEX ix_relationship_owner_id ON relationship (owner_id);

CREATE TABLE snapshot (
    group_id VARCHAR(36) NOT NULL, 
    revision INTEGER NOT NULL, 
    data JSON NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(group_id) REFERENCES "group" (id) ON DELETE RESTRICT, 
    UNIQUE (group_id)
);

CREATE TABLE access (
    relationship_id VARCHAR(36) NOT NULL, 
    user_id VARCHAR(36) NOT NULL, 
    person_id VARCHAR(36) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(person_id) REFERENCES person (id) ON DELETE RESTRICT, 
    FOREIGN KEY(relationship_id) REFERENCES relationship (id) ON DELETE RESTRICT, 
    FOREIGN KEY(user_id) REFERENCES "user" (id) ON DELETE RESTRICT, 
    UNIQUE (relationship_id, person_id), 
    UNIQUE (relationship_id, user_id)
);

CREATE INDEX ix_access_user_id ON access (user_id);

CREATE INDEX ix_access_relationship_id ON access (relationship_id);

CREATE TABLE invitation (
    sender_id VARCHAR(36) NOT NULL, 
    target_id VARCHAR(36) NOT NULL, 
    relationship_id VARCHAR(36), 
    member_id VARCHAR(36), 
    person_id VARCHAR(36) NOT NULL, 
    status VARCHAR(15) NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK ((relationship_id IS NULL) != (member_id IS NULL)), 
    FOREIGN KEY(member_id) REFERENCES member (id) ON DELETE RESTRICT, 
    FOREIGN KEY(person_id) REFERENCES person (id) ON DELETE RESTRICT, 
    FOREIGN KEY(relationship_id) REFERENCES relationship (id) ON DELETE RESTRICT, 
    FOREIGN KEY(sender_id) REFERENCES "user" (id) ON DELETE RESTRICT, 
    FOREIGN KEY(target_id) REFERENCES "user" (id) ON DELETE RESTRICT
);

CREATE INDEX ix_invitation_target_id ON invitation (target_id);

CREATE TABLE ledger (
    relationship_id VARCHAR(36) NOT NULL, 
    actor_id VARCHAR(36) NOT NULL, 
    cents BIGINT NOT NULL, 
    kind VARCHAR(32) NOT NULL, 
    description VARCHAR(500) NOT NULL, 
    date DATE NOT NULL, 
    source VARCHAR(20) NOT NULL, 
    source_id VARCHAR(36), 
    reversal_of VARCHAR(36), 
    repayment_of VARCHAR(36), 
    attachment_id VARCHAR(36), 
    operation_id VARCHAR(36) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (cents != 0 AND cents BETWEEN -100000000000 AND 100000000000), 
    FOREIGN KEY(actor_id) REFERENCES "user" (id) ON DELETE RESTRICT, 
    FOREIGN KEY(attachment_id) REFERENCES attachment (id) ON DELETE RESTRICT, 
    FOREIGN KEY(operation_id) REFERENCES operation (id) ON DELETE RESTRICT, 
    FOREIGN KEY(relationship_id) REFERENCES relationship (id) ON DELETE RESTRICT, 
    FOREIGN KEY(repayment_of) REFERENCES ledger (id) ON DELETE RESTRICT, 
    FOREIGN KEY(reversal_of) REFERENCES ledger (id) ON DELETE RESTRICT, 
    UNIQUE (reversal_of)
);

CREATE INDEX ix_ledger_date ON ledger (date);

CREATE INDEX ix_ledger_kind ON ledger (kind);

CREATE INDEX ix_ledger_relationship_id ON ledger (relationship_id);

CREATE INDEX ix_ledger_source ON ledger (source);

CREATE INDEX ix_ledger_source_id ON ledger (source_id);

CREATE INDEX ix_ledger_operation_id ON ledger (operation_id);

CREATE TABLE share (
    expense_id VARCHAR(36) NOT NULL, 
    person_id VARCHAR(36) NOT NULL, 
    cents BIGINT NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (cents >= 0), 
    FOREIGN KEY(expense_id) REFERENCES expense (id) ON DELETE RESTRICT, 
    FOREIGN KEY(person_id) REFERENCES person (id) ON DELETE RESTRICT, 
    UNIQUE (expense_id, person_id)
);

CREATE INDEX ix_share_expense_id ON share (expense_id);

CREATE TABLE review (
    user_id VARCHAR(36) NOT NULL, 
    ledger_id VARCHAR(36), 
    expense_id VARCHAR(36), 
    group_id VARCHAR(36), 
    status VARCHAR(15) NOT NULL, 
    note VARCHAR(1000) NOT NULL, 
    resolves_id VARCHAR(36), 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (status IN ('acknowledged','disputed','resolved')), 
    CHECK ((CASE WHEN ledger_id IS NULL THEN 0 ELSE 1 END + CASE WHEN expense_id IS NULL THEN 0 ELSE 1 END + CASE WHEN group_id IS NULL THEN 0 ELSE 1 END) = 1), 
    FOREIGN KEY(expense_id) REFERENCES expense (id) ON DELETE RESTRICT, 
    FOREIGN KEY(group_id) REFERENCES "group" (id) ON DELETE RESTRICT, 
    FOREIGN KEY(ledger_id) REFERENCES ledger (id) ON DELETE RESTRICT, 
    FOREIGN KEY(resolves_id) REFERENCES review (id) ON DELETE RESTRICT, 
    FOREIGN KEY(user_id) REFERENCES "user" (id) ON DELETE RESTRICT, 
    UNIQUE (resolves_id)
);

CREATE INDEX ix_review_group_id ON review (group_id);

CREATE INDEX ix_review_ledger_id ON review (ledger_id);

CREATE INDEX ix_review_expense_id ON review (expense_id);

CREATE TABLE transfer (
    snapshot_id VARCHAR(36) NOT NULL, 
    debtor_id VARCHAR(36) NOT NULL, 
    creditor_id VARCHAR(36) NOT NULL, 
    cents BIGINT NOT NULL, 
    ledger_id VARCHAR(36) NOT NULL, 
    id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (cents > 0), 
    FOREIGN KEY(creditor_id) REFERENCES person (id) ON DELETE RESTRICT, 
    FOREIGN KEY(debtor_id) REFERENCES person (id) ON DELETE RESTRICT, 
    FOREIGN KEY(ledger_id) REFERENCES ledger (id) ON DELETE RESTRICT, 
    FOREIGN KEY(snapshot_id) REFERENCES snapshot (id) ON DELETE RESTRICT, 
    UNIQUE (ledger_id)
);

CREATE INDEX ix_transfer_snapshot_id ON transfer (snapshot_id);

CREATE FUNCTION reject_financial_change() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Financial history is immutable; post a compensating event'; END $$;

CREATE TRIGGER immutable_ledger BEFORE UPDATE OR DELETE ON "ledger" FOR EACH ROW EXECUTE FUNCTION reject_financial_change();

CREATE TRIGGER immutable_share BEFORE UPDATE OR DELETE ON "share" FOR EACH ROW EXECUTE FUNCTION reject_financial_change();

CREATE TRIGGER immutable_snapshot BEFORE UPDATE OR DELETE ON "snapshot" FOR EACH ROW EXECUTE FUNCTION reject_financial_change();

CREATE TRIGGER immutable_transfer BEFORE UPDATE OR DELETE ON "transfer" FOR EACH ROW EXECUTE FUNCTION reject_financial_change();

CREATE TRIGGER immutable_audit BEFORE UPDATE OR DELETE ON "audit" FOR EACH ROW EXECUTE FUNCTION reject_financial_change();

CREATE TRIGGER immutable_review BEFORE UPDATE OR DELETE ON "review" FOR EACH ROW EXECUTE FUNCTION reject_financial_change();

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX search_person_name ON "person" USING gin ("name" gin_trgm_ops);

CREATE INDEX search_person_notes ON "person" USING gin ("notes" gin_trgm_ops);

CREATE INDEX search_ledger_description ON "ledger" USING gin ("description" gin_trgm_ops);

CREATE INDEX search_group_name ON "group" USING gin ("name" gin_trgm_ops);

CREATE INDEX search_group_description ON "group" USING gin ("description" gin_trgm_ops);

CREATE INDEX search_expense_description ON "expense" USING gin ("description" gin_trgm_ops);

CREATE INDEX ledger_history ON ledger (relationship_id, date DESC, created_at DESC, id);

CREATE INDEX group_expenses ON expense (group_id, active);

CREATE FUNCTION protect_expense() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Expense history cannot be deleted'; END IF;
        IF (to_jsonb(NEW) - 'active') IS DISTINCT FROM (to_jsonb(OLD) - 'active') OR OLD.active = false OR NEW.active = true OR OLD.group_id IS NULL THEN
          RAISE EXCEPTION 'Only active group expense supersession is permitted';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM "group" WHERE id=OLD.group_id AND status='open') THEN RAISE EXCEPTION 'Group is frozen'; END IF;
        RETURN NEW;
      END $$;

CREATE TRIGGER protect_expense BEFORE UPDATE OR DELETE ON expense FOR EACH ROW EXECUTE FUNCTION protect_expense();

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

COMMIT;

