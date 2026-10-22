"""SQLAlchemy models of clients. Tables are prefixed with `clients_`.

All three tables take part in the `org_member` policy (OrganizationOwnedMixin):
for the company itself `organization_id` is a synonym of its id.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, synonym

from src.core.infrastructure.database.base import Base, JSONType
from src.core.infrastructure.database.mixins import (
    OrganizationOwnedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    VersionMixin,
)

Amount = Numeric(18, 2)


class OrganizationModel(
    UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, OrganizationOwnedMixin, Base
):
    __tablename__ = "clients_organizations"

    inn: Mapped[str] = mapped_column(String(12), unique=True)
    ogrn: Mapped[str] = mapped_column(String(15), unique=True)
    kpp: Mapped[str | None] = mapped_column(String(9))
    legal_form: Mapped[str] = mapped_column(String(8))
    name: Mapped[str] = mapped_column(String(255))
    registered_at: Mapped[date] = mapped_column(Date)
    address: Mapped[str] = mapped_column(String(500))
    region_code: Mapped[str] = mapped_column(String(2))
    okved_main: Mapped[str] = mapped_column(String(10))
    okved_extra: Mapped[list[str]] = mapped_column(JSONType, default=list)
    tax_regime: Mapped[str] = mapped_column(String(16))
    employees_count: Mapped[int]
    registry_status: Mapped[str] = mapped_column(String(16))
    # {"last_name", "first_name", "middle_name"} of the head by the registry.
    registry_head: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    verification_status: Mapped[str] = mapped_column(String(16))
    verification_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # [{"field", "declared", "registry"}]
    verification_discrepancies: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)

    # The org_member policy filters by organization_id: here it is the row id.
    organization_id = synonym("id")  # type: ignore[assignment]


class MemberModel(OrganizationOwnedMixin, Base):
    __tablename__ = "clients_members"

    # The primary key keeps an account in a company at most once.
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("clients_organizations.id", ondelete="CASCADE"), primary_key=True
    )
    account_id: Mapped[UUID] = mapped_column(primary_key=True, index=True)
    role: Mapped[str] = mapped_column(String(16))
    authority: Mapped[str] = mapped_column(String(32))
    # {"number", "issued_at", "valid_until", "scope": [...]}
    power_of_attorney: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    added_by: Mapped[UUID | None]


class FinancialReportModel(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "clients_financial_reports"
    __table_args__ = (
        # One report per period and source. An annual report has quarter 0, not
        # NULL: NULLs are distinct in a unique constraint and would let duplicates in.
        UniqueConstraint("organization_id", "period_year", "period_quarter", "source"),
        CheckConstraint("period_quarter BETWEEN 0 AND 4", name="period_quarter"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("clients_organizations.id", ondelete="CASCADE")
    )
    period_year: Mapped[int]
    period_quarter: Mapped[int]
    source: Mapped[str] = mapped_column(String(16))
    # Roubles.
    revenue: Mapped[Decimal] = mapped_column(Amount)
    expenses: Mapped[Decimal | None] = mapped_column(Amount)
    net_profit: Mapped[Decimal | None] = mapped_column(Amount)
    total_liabilities: Mapped[Decimal | None] = mapped_column(Amount)
    monthly_debt_payments: Mapped[Decimal | None] = mapped_column(Amount)
    submitted_by: Mapped[UUID | None]
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
