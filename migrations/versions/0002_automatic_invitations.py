"""Queue phone invitations for people who have not registered yet."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("invitation", "target_id", existing_type=sa.String(36), nullable=True)
    op.add_column("invitation", sa.Column("target_phone", sa.String(20)))
    op.create_index("ix_invitation_target_phone", "invitation", ["target_phone"])
    op.execute('UPDATE invitation SET target_phone = "user".phone FROM "user" WHERE invitation.target_id = "user".id')


def downgrade():
    op.execute("DELETE FROM invitation WHERE target_id IS NULL")
    op.drop_index("ix_invitation_target_phone", table_name="invitation")
    op.drop_column("invitation", "target_phone")
    op.alter_column("invitation", "target_id", existing_type=sa.String(36), nullable=False)
