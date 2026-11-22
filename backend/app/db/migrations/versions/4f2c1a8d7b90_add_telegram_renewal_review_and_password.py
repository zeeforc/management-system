"""Add Telegram renewal review mapping and encrypted rental account passwords."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "4f2c1a8d7b90"
down_revision: str | None = "9a3d8e6f4b21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rentals",
        sa.Column("account_password_encrypted", sa.Text(), nullable=True),
    )
    op.add_column(
        "rental_renewals",
        sa.Column("telegram_review_chat_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "rental_renewals",
        sa.Column("telegram_review_message_id", sa.BigInteger(), nullable=True),
    )
    op.create_unique_constraint(
        "uq_rental_renewals_telegram_review_message",
        "rental_renewals",
        ["telegram_review_chat_id", "telegram_review_message_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_rental_renewals_telegram_review_message",
        "rental_renewals",
        type_="unique",
    )
    op.drop_column("rental_renewals", "telegram_review_message_id")
    op.drop_column("rental_renewals", "telegram_review_chat_id")
    op.drop_column("rentals", "account_password_encrypted")
