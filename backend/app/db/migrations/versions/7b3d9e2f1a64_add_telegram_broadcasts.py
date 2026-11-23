"""Add temporary Telegram broadcast campaigns and delivery tracking."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7b3d9e2f1a64"
down_revision: str | None = "4f2c1a8d7b90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_broadcasts",
        sa.Column("created_by_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("media_type", sa.String(length=16), nullable=True),
        sa.Column("media_file_id", sa.Text(), nullable=True),
        sa.Column("recipient_count", sa.Integer(), nullable=False),
        sa.Column("sent_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("ambiguous_count", sa.Integer(), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_telegram_broadcasts")),
    )
    op.create_index(
        "ix_telegram_broadcasts_status_created_at",
        "telegram_broadcasts",
        ["status", "created_at"],
        unique=False,
    )
    op.create_table(
        "telegram_broadcast_recipients",
        sa.Column("broadcast_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["broadcast_id"],
            ["telegram_broadcasts.id"],
            name=op.f("fk_telegram_broadcast_recipients_broadcast_id_telegram_broadcasts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_telegram_broadcast_recipients_customer_id_customers"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_telegram_broadcast_recipients")),
        sa.UniqueConstraint("broadcast_id", "chat_id", name="uq_broadcast_recipient_chat"),
    )
    op.create_index(
        "ix_broadcast_recipients_broadcast_status",
        "telegram_broadcast_recipients",
        ["broadcast_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_broadcast_recipients_broadcast_status",
        table_name="telegram_broadcast_recipients",
    )
    op.drop_table("telegram_broadcast_recipients")
    op.drop_index(
        "ix_telegram_broadcasts_status_created_at",
        table_name="telegram_broadcasts",
    )
    op.drop_table("telegram_broadcasts")
