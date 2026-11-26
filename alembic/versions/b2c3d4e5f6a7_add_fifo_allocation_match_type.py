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
    """新增 ``match_type`` 並 backfill ``DAY_TRADE_FIFO``。

    Side Effects:
        改 schema；將賣出 ``trade_type='DAY_TRADE'`` 之既有配對列標為
        ``DAY_TRADE_FIFO``。歷史 v2 run **無** Pass2 證據，故不猜測
        ``SAME_DAY_RECONCILED``（維持 ``STANDARD_FIFO``）。

    Financial invariants:
        不改 ``allocated_quantity``／買賣來源；僅加稽核標籤。
    """
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

    # Backfill：僅依賣出 trade_type 標記 DAY_TRADE；不猜測 SAME_DAY_RECONCILED
    op.execute(
        """
        UPDATE fifo_allocations
        SET match_type = 'DAY_TRADE_FIFO'
        WHERE sell_trade_id IN (
            SELECT id FROM trades WHERE trade_type = 'DAY_TRADE'
        )
        """
    )


def downgrade() -> None:
    """移除 ``match_type`` 欄與 check constraint。

    Lossy：``SAME_DAY_RECONCILED`` 等 v3 標籤隨欄位移除而遺失；
    之後 re-upgrade 僅能依賣出 ``trade_type`` 恢復 ``DAY_TRADE_FIFO``，
    **無法**還原 ``SAME_DAY_RECONCILED``。
    """
    with op.batch_alter_table("fifo_allocations") as batch_op:
        batch_op.drop_constraint("ck_alloc_match_type", type_="check")
        batch_op.drop_column("match_type")
