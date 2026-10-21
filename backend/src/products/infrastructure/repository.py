from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.domain import Money
from src.products.domain.product import CreditProduct, ProductStatus
from src.products.domain.value_objects import (
    LEGAL_FORMS,
    PURPOSES,
    AmountRange,
    DocumentRequirement,
    Eligibility,
    ProcessingProfile,
    ProductCode,
    RateRange,
    SecurityRequirement,
    SupportProgram,
    TermRange,
    ordered,
)
from src.products.infrastructure.models import CreditProductRecord

_PUBLISHED = (ProductStatus.ACTIVE.value, ProductStatus.ARCHIVED.value)


class SqlAlchemyProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_current(self, code: str) -> CreditProduct | None:
        stmt = (
            select(CreditProductRecord)
            .where(CreditProductRecord.code == code, CreditProductRecord.status.in_(_PUBLISHED))
            .order_by(CreditProductRecord.version.desc())
        )
        records = (await self._session.scalars(stmt)).all()
        active = [r for r in records if r.status == ProductStatus.ACTIVE.value]
        current = active or records
        return to_domain(current[0]) if current else None

    async def get_version(self, code: str, version: int) -> CreditProduct | None:
        record = await self._record(code, version)
        return None if record is None else to_domain(record)

    async def list_active(self) -> list[CreditProduct]:
        stmt = (
            select(CreditProductRecord)
            .where(CreditProductRecord.status == ProductStatus.ACTIVE.value)
            .order_by(
                CreditProductRecord.sort_order,
                CreditProductRecord.code,
                CreditProductRecord.version.desc(),
            )
        )
        latest: dict[str, CreditProductRecord] = {}
        for record in (await self._session.scalars(stmt)).all():
            latest.setdefault(record.code, record)
        return [to_domain(record) for record in latest.values()]

    async def save(self, product: CreditProduct) -> None:
        record = await self._record(product.code.value, product.version)
        if record is None:
            record = CreditProductRecord(code=product.code.value, version=product.version)
            self._session.add(record)
        write(record, product)
        await self._session.flush()

    async def _record(self, code: str, version: int) -> CreditProductRecord | None:
        stmt = select(CreditProductRecord).where(
            CreditProductRecord.code == code, CreditProductRecord.version == version
        )
        return (await self._session.scalars(stmt)).one_or_none()


def _money(value: Decimal | str | None) -> Money | None:
    return None if value is None else Money(Decimal(value))


def write(record: CreditProductRecord, product: CreditProduct) -> None:
    security = product.security
    rules = product.eligibility
    program = product.support_program
    record.status = product.status.value
    record.sort_order = product.sort_order
    record.frontend_id = product.frontend_id
    record.name = product.name
    record.short_description = product.short_description
    record.description_plain = product.description_plain
    record.purposes = list(ordered(product.purposes, PURPOSES))
    record.facility = product.facility
    record.repayment_options = list(product.repayment_options)
    record.amount_min = product.amount.min.amount
    record.amount_max = product.amount.max.amount
    record.term_min_months = product.term.min_months
    record.term_max_months = product.term.max_months
    record.rate_base = product.rate.base
    record.rate_max = product.rate.max
    record.collateral_kind = security.collateral
    record.collateral_types = list(security.collateral_types)
    record.collateral_required_from = (
        None if security.required_from is None else security.required_from.amount
    )
    record.guarantee = security.guarantee
    record.target_use_confirmation = product.target_use_confirmation
    record.support_program = (
        None
        if program is None
        else {
            "code": program.code,
            "name": program.name,
            "rate_cap": str(program.rate_cap),
            "msp_registry_required": program.msp_registry_required,
            "okved_whitelist": sorted(program.okved_whitelist),
        }
    )
    record.min_business_age_months = rules.min_business_age_months
    record.allowed_legal_forms = list(ordered(rules.allowed_legal_forms, LEGAL_FORMS))
    record.min_annual_revenue = (
        None if rules.min_annual_revenue is None else rules.min_annual_revenue.amount
    )
    record.required_documents = [
        {
            "type": d.type,
            "title": d.title,
            "required_from_amount": None
            if d.required_from is None
            else str(d.required_from.amount),
            "legal_forms": list(ordered(d.legal_forms, LEGAL_FORMS)),
        }
        for d in product.required_documents
    ]
    record.application_fields_schema = dict(product.application_fields_schema)
    record.workflow_code = product.processing.workflow_code
    record.auto_decision_limit = product.processing.auto_decision_limit.amount


def to_domain(record: CreditProductRecord) -> CreditProduct:
    program: dict[str, Any] | None = record.support_program
    return CreditProduct(
        code=ProductCode(record.code),
        version=record.version,
        status=ProductStatus(record.status),
        name=record.name,
        short_description=record.short_description,
        description_plain=record.description_plain,
        frontend_id=record.frontend_id,
        purposes=frozenset(record.purposes),
        facility=record.facility,
        repayment_options=tuple(record.repayment_options),
        amount=AmountRange(Money(record.amount_min), Money(record.amount_max)),
        term=TermRange(record.term_min_months, record.term_max_months),
        rate=RateRange(Decimal(record.rate_base), Decimal(record.rate_max)),
        security=SecurityRequirement(
            collateral=record.collateral_kind,
            collateral_types=tuple(record.collateral_types),
            guarantee=record.guarantee,
            required_from=_money(record.collateral_required_from),
        ),
        eligibility=Eligibility(
            min_business_age_months=record.min_business_age_months,
            allowed_legal_forms=frozenset(record.allowed_legal_forms),
            min_annual_revenue=_money(record.min_annual_revenue),
        ),
        processing=ProcessingProfile(
            workflow_code=record.workflow_code,
            auto_decision_limit=Money(record.auto_decision_limit),
        ),
        required_documents=tuple(
            DocumentRequirement(
                type=d["type"],
                title=d["title"],
                required_from=_money(d.get("required_from_amount")),
                legal_forms=frozenset(d.get("legal_forms", ())),
            )
            for d in record.required_documents
        ),
        support_program=None
        if program is None
        else SupportProgram(
            code=program["code"],
            name=program["name"],
            rate_cap=Decimal(program["rate_cap"]),
            msp_registry_required=bool(program["msp_registry_required"]),
            okved_whitelist=frozenset(program["okved_whitelist"]),
        ),
        target_use_confirmation=record.target_use_confirmation,
        application_fields_schema=dict(record.application_fields_schema),
        sort_order=record.sort_order,
    )
