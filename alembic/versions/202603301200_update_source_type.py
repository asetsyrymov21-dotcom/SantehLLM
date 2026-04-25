"""update source type values"""

from alembic import op

revision = "202603301200"
down_revision = "202603292230"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE sourcetype ADD VALUE IF NOT EXISTS 'telegram_text'")
    op.execute("ALTER TYPE sourcetype ADD VALUE IF NOT EXISTS 'telegram_voice'")
    op.execute("ALTER TYPE sourcetype ADD VALUE IF NOT EXISTS 'file'")


def downgrade() -> None:
    # PostgreSQL cannot easily remove enum values; leave as-is
    pass
