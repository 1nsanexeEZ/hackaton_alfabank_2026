from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.decision.application.ports import PreApprovalBasis, PreApprovedOffer
from src.modules.decision.domain.model import Outcome
from src.modules.decision.domain.result import DecidedByType, DecisionResult
from src.modules.decision.infrastructure.models import DecisionResultRecord, PreApprovedOfferRecord
from src.modules.decision.infrastructure.serialization import (
    dump_info,
    dump_inputs,
    dump_limits,
    dump_terms,
    dump_trace,
    load_info,
    load_inputs,
    load_limits,
    load_terms,
    load_trace,
)


class SqlAlchemyDecisionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, result: DecisionResult) -> None:
        # Команды по заявке идут по одному ключу Kafka — последовательно; гонку ловит
        # уникальность (application_id, sequence), обработчик повторит команду.
        stmt = select(func.max(DecisionResultRecord.sequence)).where(
            DecisionResultRecord.application_id == result.application_id
        )
        last = (await self._session.scalars(stmt)).one()
        self._session.add(_to_record(result, (last or 0) + 1))
        await self._session.flush()

    async def get_by_command(self, command_event_id: UUID) -> DecisionResult | None:
        stmt = select(DecisionResultRecord).where(
            DecisionResultRecord.requested_by_command == command_event_id
        )
        record = (await self._session.scalars(stmt)).one_or_none()
        return _to_domain(record) if record is not None else None

    async def latest_for_application(self, application_id: UUID) -> DecisionResult | None:
        return await self._latest(application_id)

    async def latest_automatic(self, application_id: UUID) -> DecisionResult | None:
        return await self._latest(application_id, decided_by_type="auto")

    async def _latest(
        self, application_id: UUID, decided_by_type: str | None = None
    ) -> DecisionResult | None:
        stmt = select(DecisionResultRecord).where(
            DecisionResultRecord.application_id == application_id
        )
        if decided_by_type is not None:
            stmt = stmt.where(DecisionResultRecord.decided_by_type == decided_by_type)
        stmt = stmt.order_by(DecisionResultRecord.sequence.desc()).limit(1)
        record = (await self._session.scalars(stmt)).first()
        return _to_domain(record) if record is not None else None


class SqlAlchemyPreApprovedOfferRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_organization(
        self, organization_id: UUID, offers: Sequence[PreApprovedOffer]
    ) -> None:
        await self._session.execute(
            delete(PreApprovedOfferRecord).where(
                PreApprovedOfferRecord.organization_id == organization_id
            )
        )
        self._session.add_all(
            [_offer_record(offer) for offer in offers if offer.organization_id == organization_id]
        )
        await self._session.flush()

    async def list_for_organization(self, organization_id: UUID) -> list[PreApprovedOffer]:
        stmt = (
            select(PreApprovedOfferRecord)
            .where(PreApprovedOfferRecord.organization_id == organization_id)
            .order_by(PreApprovedOfferRecord.max_amount.desc(), PreApprovedOfferRecord.product_code)
        )
        return [_offer(record) for record in await self._session.scalars(stmt)]


def _to_record(result: DecisionResult, sequence: int) -> DecisionResultRecord:
    return DecisionResultRecord(
        id=result.id,
        application_id=result.application_id,
        sequence=sequence,
        requested_by_command=result.requested_by_command,
        policy_version=result.policy_version,
        key_rate=result.key_rate,
        inputs=dump_inputs(result.inputs),
        outcome=result.outcome,
        terms=dump_terms(result.terms),
        alternative_product_code=result.alternative_product_code,
        reason_codes=list(result.reason_codes),
        client_explanation=result.client_explanation,
        improvement_hints=list(result.improvement_hints),
        requested_info=dump_info(result.requested_info),
        rule_trace=dump_trace(result.rule_trace),
        limits=dump_limits(result.limits),
        decided_by_type=result.decided_by_type,
        decided_by_id=result.decided_by_id,
        override_of=result.override_of,
        comment=result.comment,
        decided_at=result.decided_at,
    )


def _to_domain(record: DecisionResultRecord) -> DecisionResult:
    return DecisionResult(
        id=record.id,
        application_id=record.application_id,
        requested_by_command=record.requested_by_command,
        policy_version=record.policy_version,
        key_rate=Decimal(str(record.key_rate)),
        inputs=load_inputs(record.inputs),
        outcome=cast(Outcome, record.outcome),
        terms=load_terms(record.terms),
        alternative_product_code=record.alternative_product_code,
        reason_codes=tuple(record.reason_codes),
        client_explanation=record.client_explanation,
        improvement_hints=tuple(record.improvement_hints),
        requested_info=load_info(record.requested_info),
        rule_trace=load_trace(record.rule_trace),
        limits=load_limits(record.limits),
        decided_by_type=cast(DecidedByType, record.decided_by_type),
        decided_by_id=record.decided_by_id,
        override_of=record.override_of,
        comment=record.comment,
        decided_at=record.decided_at,
    )


def _offer_record(offer: PreApprovedOffer) -> PreApprovedOfferRecord:
    return PreApprovedOfferRecord(
        organization_id=offer.organization_id,
        product_code=offer.product_code,
        max_amount=offer.max_amount,
        rate_from=offer.rate_from,
        term_max_months=offer.term_max_months,
        basis=offer.basis,
        factors_summary=list(offer.factors_summary),
        valid_until=offer.valid_until,
        computed_at=offer.computed_at,
    )


def _offer(record: PreApprovedOfferRecord) -> PreApprovedOffer:
    return PreApprovedOffer(
        organization_id=record.organization_id,
        product_code=record.product_code,
        max_amount=Decimal(str(record.max_amount)),
        rate_from=Decimal(str(record.rate_from)),
        term_max_months=record.term_max_months,
        basis=cast(PreApprovalBasis, record.basis),
        factors_summary=tuple(record.factors_summary),
        valid_until=record.valid_until,
        computed_at=record.computed_at,
    )
