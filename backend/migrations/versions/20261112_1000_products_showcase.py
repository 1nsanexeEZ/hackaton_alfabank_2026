"""products: the showcase card — short words, a label and the decision time

Revision ID: products_0003
Revises: projector_0002
Create Date: 2026-11-12 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "products_0003"
down_revision: str | None = "projector_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "products_credit_products"
# The demo catalog's cards, as the frontend showed them by the code before (seed/products.py).
SHOWCASE = {
    "UNSECURED": (["Без залога", "Быстро", "На любые цели"], "Популярный", "5 минут"),
    "SECURED": (["Крупная сумма", "Надолго", "Ставка ниже"], None, "1 рабочий день"),
    "CREDIT_LINE": (["Частями", "Свой лимит", "Гибко"], None, "1 рабочий день"),
    "OVERDRAFT": (["Кассовый разрыв", "Сразу", "Подушка"], None, "5 минут"),
    "AUTO": (["Транспорт", "Залог — покупка", "До 7 лет"], None, "1 рабочий день"),
    "MORTGAGE": (["Недвижимость", "До 10 лет", "Для ООО и АО"], None, "3 рабочих дня"),
    "REFINANCE": (["Один платёж", "Ставка ниже", "Один график"], None, "1 рабочий день"),
    "GOV_SUPPORT": (["Льготная ставка", "Господдержка", "МСП"], None, "1 рабочий день"),
    "STARTUP": (["Новый бизнес", "Без оборотов", "Господдержка"], "До 6 месяцев", "3 рабочих дня"),
}


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("keywords", postgresql.JSONB(), nullable=True))
    op.add_column(TABLE, sa.Column("tag", sa.String(40), nullable=True))
    op.add_column(TABLE, sa.Column("decision_time", sa.String(40), nullable=True))
    products = sa.table(
        TABLE,
        sa.column("code", sa.String),
        sa.column("keywords", postgresql.JSONB),
        sa.column("tag", sa.String),
        sa.column("decision_time", sa.String),
    )
    op.execute(products.update().values(keywords=[]))
    for code, (keywords, tag, decision_time) in SHOWCASE.items():
        op.execute(
            products.update()
            .where(products.c.code == code)
            .values(keywords=keywords, tag=tag, decision_time=decision_time)
        )
    op.alter_column(TABLE, "keywords", nullable=False)


def downgrade() -> None:
    op.drop_column(TABLE, "decision_time")
    op.drop_column(TABLE, "tag")
    op.drop_column(TABLE, "keywords")
