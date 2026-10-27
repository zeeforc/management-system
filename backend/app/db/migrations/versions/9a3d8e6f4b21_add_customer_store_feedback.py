"""Add persistent customer ratings and store feedback."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9a3d8e6f4b21"
down_revision: str | None = "c84b29f1a5d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "store_feedback",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("customer_display_name", sa.String(length=160), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("channel_message_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "rating >= 1 AND rating <= 5",
            name=op.f("ck_store_feedback_rating_range"),
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="fk_store_feedback_customer_id_customers",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_store_feedback"),
    )
    op.create_index(
        "ix_store_feedback_customer_id",
        "store_feedback",
        ["customer_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_store_feedback_customer_id", table_name="store_feedback")
    op.drop_table("store_feedback")
