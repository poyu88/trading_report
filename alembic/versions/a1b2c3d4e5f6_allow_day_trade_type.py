"""allow DAY_TRADE trade_type

Revision ID: a1b2c3d4e5f6
Revises: 5d328560b3b3
Create Date: 2026-11-20 21:30:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "5d328560b3b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("trades") as batch_op:
        batch_op.drop_constraint("ck_trade_type", type_="check")
        batch_op.create_check_constraint(
            "ck_trade_type",
            "trade_type IN ('CASH', 'DAY_TRADE')",
        )


def downgrade() -> None:
    with op.batch_alter_table("trades") as batch_op:
        batch_op.drop_constraint("ck_trade_type", type_="check")
        batch_op.create_check_constraint(
            "ck_trade_type",
            "trade_type = 'CASH'",
        )
