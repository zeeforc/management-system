"""Add encrypted account details to rentals and profile/PIN product option."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c84b29f1a5d7"
down_revision: Union[str, None] = "62fa14b676c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "has_profile_pin",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column("rentals", sa.Column("account_email_encrypted", sa.Text(), nullable=True))
    op.add_column("rentals", sa.Column("profile_encrypted", sa.Text(), nullable=True))
    op.add_column("rentals", sa.Column("pin_encrypted", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("rentals", "pin_encrypted")
    op.drop_column("rentals", "profile_encrypted")
    op.drop_column("rentals", "account_email_encrypted")
    op.drop_column("products", "has_profile_pin")
