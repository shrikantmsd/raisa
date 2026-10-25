"""0005 intelligence audit event types

Revision ID: 5c53e7aba45e
Revises: f11f36a94de1
Create Date: 2026-09-28 01:04:24.457311

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5c53e7aba45e'
down_revision = 'f11f36a94de1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Hand-written: Alembic doesn't autogenerate new labels on an existing
    # Postgres enum type (same reason as 0002-0004).
    op.execute("ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'INTELLIGENCE_CREATED'")
    op.execute("ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'INTELLIGENCE_UPDATED'")
    op.execute("ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'INTELLIGENCE_STATUS_CHANGED'")
    op.execute("ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'INTELLIGENCE_CLASSIFICATION_CHANGED'")
    op.execute("ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'INTELLIGENCE_DISTRIBUTED'")
    op.execute("ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'INTELLIGENCE_SOURCE_CHANGED'")


def downgrade() -> None:
    # Postgres cannot drop enum labels; intentionally a no-op. Leaving the
    # extra labels in place is harmless to older code.
    pass
