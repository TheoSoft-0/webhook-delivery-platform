"""add worker lease fields to outbox messages

Revision ID: 4a21fc24cd4f
Revises: 2c83794b6e5b
Create Date: 2026-11-15 13:14:08.828098

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4a21fc24cd4f"
down_revision: str | Sequence[str] | None = "2c83794b6e5b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        "outbox_messages",
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        schema="webhook",
    )

    op.add_column(
        "outbox_messages",
        sa.Column(
            "lease_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        schema="webhook",
    )

    op.create_check_constraint(
        "ck_outbox_messages_lease_state",
        "outbox_messages",
        """
        (
            lease_token IS NULL
            AND lease_expires_at IS NULL
        )
        OR
        (
            status = 'published'
            AND lease_token IS NOT NULL
            AND lease_expires_at IS NOT NULL
        )
        """,
        schema="webhook",
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint(
        "ck_outbox_messages_lease_state",
        "outbox_messages",
        schema="webhook",
        type_="check",
    )

    op.drop_column(
        "outbox_messages",
        "lease_expires_at",
        schema="webhook",
    )

    op.drop_column(
        "outbox_messages",
        "lease_token",
        schema="webhook",
    )
