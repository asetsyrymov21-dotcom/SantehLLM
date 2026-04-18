"""add cancelled sale status"""

from alembic import op

revision = "202603301300"
down_revision = "202603301200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE salestatus ADD VALUE IF NOT EXISTS 'cancelled'")


def downgrade() -> None:
    # cannot easily remove enum value
    pass
