from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions.exceptions import ConflictError, NotFoundError
from src.modules.decision.application.ports import (
    FounderPrescreen,
    PreApprovalBasis,
    PreApprovedOffer,
    PrescreenCheck,
    PrescreenStatus,
    ProjectAssessment,
    ProjectCheck,
    ProjectFigures,
    ProjectStatus,
)
from src.modules.decision.domain.model import Outcome
from src.modules.decision.domain.policy_version import PolicyStatus, PolicyVersion
from src.modules.decision.domain.result import DecidedByType, DecisionResult
from src.modules.decision.infrastructure.models import (
    DecisionPolicyVersionRecord,
    DecisionResultRecord,
    FounderPrescreenRecord,
    PreApprovedOfferRecord,
    ProjectAssessmentRecord,
)
from src.modules.decision.infrastructure.serialization import (
    dump_info,
    dump_inputs,
    dump_limits,
    dump_rate_breakdown,
    dump_terms,
    dump_trace,
    dump_triggers,
    load_info,
    load_inputs,
    load_limits,
    load_rate_breakdown,
    load_terms,
    load_trace,
    load_triggers,
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

    async def recent_automatic(self, limit: int) -> list[DecisionResult]:
        """Последнее автоматическое решение по каждой из `limit` заявок со свежими такими
        решениями: повторное решение той же заявки не считается дважды."""
        latest = (
            select(
                DecisionResultRecord.application_id,
                func.max(DecisionResultRecord.sequence).label("sequence"),
            )
            .where(DecisionResultRecord.decided_by_type == "auto")
            .group_by(DecisionResultRecord.application_id)
            .subquery()
        )
        stmt = (
            select(DecisionResultRecord)
            .join(
                latest,
                (DecisionResultRecord.application_id == latest.c.application_id)
                & (DecisionResultRecord.sequence == latest.c.sequence),
            )
            .order_by(DecisionResultRecord.decided_at.desc(), DecisionResultRecord.id)
            .limit(limit)
        )
        return [_to_domain(record) for record in (await self._session.scalars(stmt)).all()]


class SqlAlchemyPolicyVersionRepository:
    """Версии политики админа. Активной бывает одна (частичный уникальный индекс): гонку двух
    активаций проигравший получает как 409."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[PolicyVersion]:
        stmt = select(DecisionPolicyVersionRecord).order_by(
            DecisionPolicyVersionRecord.created_at, DecisionPolicyVersionRecord.version
        )
        return [_version_to_domain(r) for r in (await self._session.scalars(stmt)).all()]

    async def get(self, version: str) -> PolicyVersion | None:
        record = await self._session.get(DecisionPolicyVersionRecord, version)
        return _version_to_domain(record) if record is not None else None

    async def codes(self) -> list[str]:
        stmt = select(DecisionPolicyVersionRecord.version)
        return list((await self._session.scalars(stmt)).all())

    async def active_version(self) -> str | None:
        stmt = select(DecisionPolicyVersionRecord.version).where(
            DecisionPolicyVersionRecord.status == "active"
        )
        return (await self._session.scalars(stmt)).one_or_none()

    async def add(self, version: PolicyVersion) -> None:
        self._session.add(
            DecisionPolicyVersionRecord(
                version=version.version,
                status=version.status,
                body=version.body,
                based_on=version.based_on,
                comment=version.comment,
                created_by=version.created_by,
                created_at=version.created_at,
                updated_at=version.updated_at,
                activated_by=version.activated_by,
                activated_at=version.activated_at,
            )
        )
        await self._flush(version.version)

    async def save(self, version: PolicyVersion) -> None:
        record = await self._session.get(DecisionPolicyVersionRecord, version.version)
        if record is None:
            raise NotFoundError("Policy version not found", details={"version": version.version})
        record.status = version.status
        record.body = version.body
        record.comment = version.comment
        record.updated_at = cast(datetime, version.updated_at)
        record.activated_by = version.activated_by
        record.activated_at = version.activated_at
        # Flush после каждой записи: архив прежней активной должен попасть в БД раньше новой
        # активной, иначе сработает уникальный индекс.
        await self._flush(version.version)

    async def delete(self, version: str) -> None:
        await self._session.execute(
            delete(DecisionPolicyVersionRecord).where(
                DecisionPolicyVersionRecord.version == version
            )
        )
        await self._session.flush()

    async def _flush(self, version: str) -> None:
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError(
                "Policy version changed concurrently", details={"version": version}
            ) from exc


def _version_to_domain(record: DecisionPolicyVersionRecord) -> PolicyVersion:
    return PolicyVersion(
        version=record.version,
        status=cast(PolicyStatus, record.status),
        body=record.body,
        based_on=record.based_on,
        comment=record.comment,
        created_by=record.created_by,
        created_at=record.created_at,
        updated_at=record.updated_at,
        activated_by=record.activated_by,
        activated_at=record.activated_at,
    )


class SqlAlchemyPreApprovedOfferRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_organization(
        self, organization_id: UUID, offers: Sequence[PreApprovedOffer]
    ) -> None:
        await self._replace(organization_id, offers, project=False)

    async def replace_project_offers(
        self, organization_id: UUID, offers: Sequence[PreApprovedOffer]
    ) -> None:
        await self._replace(organization_id, offers, project=True)

    async def _replace(
        self, organization_id: UUID, offers: Sequence[PreApprovedOffer], *, project: bool
    ) -> None:
        """Предложения по оценке без заявки и проектные приходят из разных оценок: каждая
        перезаписывает только свои."""
        is_project = PreApprovedOfferRecord.basis == "project"
        await self._session.execute(
            delete(PreApprovedOfferRecord).where(
                PreApprovedOfferRecord.organization_id == organization_id,
                is_project if project else ~is_project,
            )
        )
        self._session.add_all(
            [
                _offer_record(offer)
                for offer in offers
                if offer.organization_id == organization_id
                and (offer.basis == "project") == project
            ]
        )
        await self._session.flush()

    async def list_for_organization(self, organization_id: UUID) -> list[PreApprovedOffer]:
        stmt = (
            select(PreApprovedOfferRecord)
            .where(PreApprovedOfferRecord.organization_id == organization_id)
            .order_by(PreApprovedOfferRecord.max_amount.desc(), PreApprovedOfferRecord.product_code)
        )
        return [_offer(record) for record in await self._session.scalars(stmt)]

    async def organizations_expiring_by(self, day: date, limit: int) -> list[UUID]:
        soonest = func.min(PreApprovedOfferRecord.valid_until)
        stmt = (
            select(PreApprovedOfferRecord.organization_id)
            # Проектное предложение пересчёт по оценке не продлевает: его даёт новая оценка.
            .where(PreApprovedOfferRecord.basis != "project")
            .group_by(PreApprovedOfferRecord.organization_id)
            .having(soonest <= day)
            .order_by(soonest, PreApprovedOfferRecord.organization_id)
            .limit(limit)
        )
        return list(await self._session.scalars(stmt))


class SqlAlchemyFounderPrescreenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, prescreen: FounderPrescreen) -> None:
        self._session.add(
            FounderPrescreenRecord(
                id=prescreen.id,
                organization_id=prescreen.organization_id,
                founder_account_id=prescreen.founder_account_id,
                founder_name=prescreen.founder_name,
                status=prescreen.status,
                reasons=[
                    {"code": r.code, "passed": r.passed, "message": r.message}
                    for r in prescreen.reasons
                ],
                version=prescreen.version,
                checked_at=prescreen.checked_at,
                valid_until=prescreen.valid_until,
            )
        )
        await self._session.flush()

    async def latest_for_organization(self, organization_id: UUID) -> FounderPrescreen | None:
        stmt = (
            select(FounderPrescreenRecord)
            .where(FounderPrescreenRecord.organization_id == organization_id)
            .order_by(FounderPrescreenRecord.checked_at.desc(), FounderPrescreenRecord.id)
            .limit(1)
        )
        record = (await self._session.scalars(stmt)).first()
        if record is None:
            return None
        return FounderPrescreen(
            id=record.id,
            organization_id=record.organization_id,
            founder_account_id=record.founder_account_id,
            founder_name=record.founder_name,
            status=cast(PrescreenStatus, record.status),
            reasons=tuple(
                PrescreenCheck(r["code"], r["passed"], r["message"]) for r in record.reasons
            ),
            version=record.version,
            checked_at=_aware(record.checked_at),
            valid_until=_aware(record.valid_until),
        )


class SqlAlchemyProjectAssessmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, assessment: ProjectAssessment) -> None:
        figures = assessment.figures
        self._session.add(
            ProjectAssessmentRecord(
                id=assessment.id,
                organization_id=assessment.organization_id,
                product_code=assessment.product_code,
                plan_revision=assessment.plan_revision,
                status=assessment.status,
                reasons=[
                    {"code": r.code, "passed": r.passed, "message": r.message}
                    for r in assessment.reasons
                ],
                figures={
                    "requested_amount": str(figures.requested_amount),
                    "term_months": figures.term_months,
                    "rate": str(figures.rate),
                    "cash_flow": str(figures.cash_flow),
                    "debt_service": str(figures.debt_service),
                    "dscr": str(figures.dscr) if figures.dscr is not None else None,
                    "own_share": str(figures.own_share),
                    "coverage": str(figures.coverage),
                    "capacity": str(figures.capacity),
                },
                max_amount=assessment.max_amount,
                version=assessment.version,
                checked_at=assessment.checked_at,
                valid_until=assessment.valid_until,
            )
        )
        await self._session.flush()

    async def latest_for_organization(self, organization_id: UUID) -> ProjectAssessment | None:
        stmt = (
            select(ProjectAssessmentRecord)
            .where(ProjectAssessmentRecord.organization_id == organization_id)
            .order_by(ProjectAssessmentRecord.checked_at.desc(), ProjectAssessmentRecord.id)
            .limit(1)
        )
        record = (await self._session.scalars(stmt)).first()
        if record is None:
            return None
        figures = record.figures
        return ProjectAssessment(
            id=record.id,
            organization_id=record.organization_id,
            product_code=record.product_code,
            plan_revision=record.plan_revision,
            status=cast(ProjectStatus, record.status),
            reasons=tuple(
                ProjectCheck(r["code"], r["passed"], r["message"]) for r in record.reasons
            ),
            figures=ProjectFigures(
                requested_amount=Decimal(figures["requested_amount"]),
                term_months=int(figures["term_months"]),
                rate=Decimal(figures["rate"]),
                cash_flow=Decimal(figures["cash_flow"]),
                debt_service=Decimal(figures["debt_service"]),
                dscr=Decimal(figures["dscr"]) if figures["dscr"] is not None else None,
                own_share=Decimal(figures["own_share"]),
                coverage=Decimal(figures["coverage"]),
                capacity=Decimal(figures["capacity"]),
            ),
            max_amount=Decimal(str(record.max_amount)) if record.max_amount is not None else None,
            version=record.version,
            checked_at=_aware(record.checked_at),
            valid_until=_aware(record.valid_until),
        )


def _aware(moment: datetime) -> datetime:
    """SQLite отдаёт время без зоны; храним в UTC."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


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
        triggers=dump_triggers(result.triggers),
        rate_breakdown=dump_rate_breakdown(result.rate_breakdown),
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
        triggers=load_triggers(record.triggers),
        rate_breakdown=load_rate_breakdown(record.rate_breakdown),
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
