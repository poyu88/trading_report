"""add fifo_allocations.match_type

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-26 12:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("fifo_allocations") as batch_op:
        batch_op.add_column(
            sa.Column(
                "match_type",
                sa.String(length=32),
                nullable=False,
                server_default="STANDARD_FIFO",
            )
        )
        batch_op.create_check_constraint(
            "ck_alloc_match_type",
            "match_type IN ('STANDARD_FIFO', 'SAME_DAY_RECONCILED', 'DAY_TRADE_FIFO')",
        )


def downgrade() -> None:
    with op.batch_alter_table("fifo_allocations") as batch_op:
        batch_op.drop_constraint("ck_alloc_match_type", type_="check")
        batch_op.drop_column("match_type")
