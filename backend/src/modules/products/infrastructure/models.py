"""SQLAlchemy models of products. Tables are prefixed with `products_`."""

from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, CheckConstraint, Numeric, String, Text, UniqueConstraint, false
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.infrastructure.database.base import Base, JSONType
from src.core.infrastructure.database.mixins import TimestampMixin, UUIDPrimaryKeyMixin

MONEY = Numeric(18, 2)
RATE = Numeric(5, 2)
# Same column type as JSONType, but Python None is SQL NULL, not JSON `null`.
NULLABLE_JSON = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")


class CreditProductRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One version of a credit product: terms change as a new version, so an
    application keeps pointing to what the client saw."""

    __tablename__ = "products_credit_products"
    __table_args__ = (
        UniqueConstraint("code", "version"),
        CheckConstraint("status IN ('draft', 'active', 'archived')", name="status"),
        CheckConstraint("amount_min > 0 AND amount_min <= amount_max", name="amount_range"),
        CheckConstraint(
            "term_min_months >= 1 AND term_min_months <= term_max_months", name="term_range"
        ),
        CheckConstraint("rate_base >= 0 AND rate_base <= rate_max", name="rate_range"),
    )

    code: Mapped[str] = mapped_column(String(32))
    version: Mapped[int]
    status: Mapped[str] = mapped_column(String(16))
    sort_order: Mapped[int] = mapped_column(default=0)
    frontend_id: Mapped[str] = mapped_column(String(32))
    # The showcase card: words, a label and the decision time.
    keywords: Mapped[list[str]] = mapped_column(JSONType, default=list)
    tag: Mapped[str | None] = mapped_column(String(40))
    decision_time: Mapped[str | None] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    short_description: Mapped[str] = mapped_column(String(500))
    description_plain: Mapped[str] = mapped_column(Text)
    # ["working_capital", ...]
    purposes: Mapped[list[str]] = mapped_column(JSONType)
    facility: Mapped[str] = mapped_column(String(32))
    # ["annuity", "differentiated"]: the first one is the default
    repayment_options: Mapped[list[str]] = mapped_column(JSONType)
    amount_min: Mapped[Decimal] = mapped_column(MONEY)
    amount_max: Mapped[Decimal] = mapped_column(MONEY)
    term_min_months: Mapped[int]
    term_max_months: Mapped[int]
    rate_base: Mapped[Decimal] = mapped_column(RATE)
    rate_max: Mapped[Decimal] = mapped_column(RATE)
    collateral_kind: Mapped[str] = mapped_column(String(16))
    # ["real_estate", "vehicle"]
    collateral_types: Mapped[list[str]] = mapped_column(JSONType)
    collateral_required_from: Mapped[Decimal | None] = mapped_column(MONEY)
    guarantee: Mapped[str] = mapped_column(String(32))
    target_use_confirmation: Mapped[bool]
    # {"code", "name", "rate_cap": "15", "msp_registry_required", "okved_whitelist": [...]}
    support_program: Mapped[dict[str, Any] | None] = mapped_column(NULLABLE_JSON)
    min_business_age_months: Mapped[int]
    # ["LLC", "IE", "JSC"]
    allowed_legal_forms: Mapped[list[str]] = mapped_column(JSONType)
    min_annual_revenue: Mapped[Decimal | None] = mapped_column(MONEY)
    # Only a company without turnover (products_0002).
    startup_only: Mapped[bool] = mapped_column(default=False, server_default=false())
    # [{"type", "title", "required_from_amount": "5000000.00" | null, "legal_forms": [...]}]
    required_documents: Mapped[list[dict[str, Any]]] = mapped_column(JSONType)
    # JSON Schema of the extra application form fields
    application_fields_schema: Mapped[dict[str, Any]] = mapped_column(JSONType)
    workflow_code: Mapped[str] = mapped_column(String(64))
    auto_decision_limit: Mapped[Decimal] = mapped_column(MONEY)
