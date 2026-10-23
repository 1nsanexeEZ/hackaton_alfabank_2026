from __future__ import annotations

from datetime import UTC, date
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.scoring.application.serialization import (
    dump_client_features,
    load_client_features,
)
from src.modules.scoring.domain.client_features import FeatureSnapshot
from src.modules.scoring.domain.model import (
    Direction,
    Factor,
    Grade,
    MlScore,
    RiskFlag,
    ScoringResult,
    Segment,
)
from src.modules.scoring.domain.quality import QualityLevel
from src.modules.scoring.infrastructure.models import FeatureSnapshotRecord, ScoringResultRecord


class SqlAlchemyScoringRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, result: ScoringResult, *, input_snapshot: dict[str, Any]) -> None:
        self._session.add(_to_record(result, input_snapshot))
        await self._session.flush()

    async def get_by_command(self, command_event_id: UUID) -> ScoringResult | None:
        stmt = select(ScoringResultRecord).where(
            ScoringResultRecord.requested_by_command == command_event_id
        )
        record = (await self._session.scalars(stmt)).one_or_none()
        return _to_domain(record) if record is not None else None

    async def latest_for_application(self, application_id: UUID) -> ScoringResult | None:
        stmt = (
            select(ScoringResultRecord)
            .where(ScoringResultRecord.application_id == application_id)
            .order_by(ScoringResultRecord.computed_at.desc(), ScoringResultRecord.id)
        )
        record = (await self._session.scalars(stmt)).first()
        return _to_domain(record) if record is not None else None


class SqlAlchemyFeatureSnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, snapshot: FeatureSnapshot) -> None:
        self._session.add(
            FeatureSnapshotRecord(
                id=snapshot.id,
                organization_id=snapshot.organization_id,
                as_of=snapshot.as_of,
                collected_at=snapshot.collected_at,
                enrichment_snapshot_id=snapshot.enrichment_snapshot_id,
                features=dump_client_features(snapshot.features),
                sources=list(snapshot.sources),
                version=snapshot.version,
            )
        )
        await self._session.flush()

    async def get_by_enrichment_snapshot(self, snapshot_id: UUID) -> FeatureSnapshot | None:
        stmt = select(FeatureSnapshotRecord).where(
            FeatureSnapshotRecord.enrichment_snapshot_id == snapshot_id
        )
        record = (await self._session.scalars(stmt)).first()
        return _snapshot_to_domain(record) if record is not None else None

    async def latest(self, organization_id: UUID, *, since: date) -> FeatureSnapshot | None:
        stmt = (
            select(FeatureSnapshotRecord)
            .where(
                FeatureSnapshotRecord.organization_id == organization_id,
                FeatureSnapshotRecord.as_of >= since,
            )
            .order_by(FeatureSnapshotRecord.collected_at.desc(), FeatureSnapshotRecord.id)
        )
        record = (await self._session.scalars(stmt)).first()
        return _snapshot_to_domain(record) if record is not None else None


def _snapshot_to_domain(record: FeatureSnapshotRecord) -> FeatureSnapshot:
    collected_at = record.collected_at
    # sqlite в тестах отдаёт время без зоны; храним всегда UTC.
    if collected_at.tzinfo is None:
        collected_at = collected_at.replace(tzinfo=UTC)
    return FeatureSnapshot(
        id=record.id,
        organization_id=record.organization_id,
        as_of=record.as_of,
        collected_at=collected_at,
        enrichment_snapshot_id=record.enrichment_snapshot_id,
        features=load_client_features(record.features),
        sources=tuple(record.sources),
        version=record.version,
    )


def _to_record(result: ScoringResult, input_snapshot: dict[str, Any]) -> ScoringResultRecord:
    return ScoringResultRecord(
        id=result.id,
        application_id=result.application_id,
        requested_by_command=result.requested_by_command,
        model_version=result.model_version,
        input_snapshot=input_snapshot,
        input_hash=result.input_hash,
        score=result.score,
        grade=result.grade,
        factors=[_factor_to_json(f) for f in result.factors],
        flags=list(result.flags),
        bank_notes=list(result.bank_notes),
        data_completeness=result.data_completeness,
        computed_at=result.computed_at,
        segment=result.segment,
        scorecard=result.scorecard,
        pd_12m=result.pd_12m,
        reason_codes=list(result.reason_codes) if result.pd_12m is not None else None,
        ml=_ml_to_json(result.ml) if result.ml is not None else None,
        quality=result.quality,
        quality_reasons=list(result.quality_reasons) if result.quality is not None else None,
    )


def _to_domain(record: ScoringResultRecord) -> ScoringResult:
    return ScoringResult(
        id=record.id,
        application_id=record.application_id,
        requested_by_command=record.requested_by_command,
        model_version=record.model_version,
        score=record.score,
        grade=cast(Grade, record.grade),
        factors=tuple(_factor_from_json(f) for f in record.factors),
        flags=tuple(cast(RiskFlag, flag) for flag in record.flags),
        data_completeness=Decimal(str(record.data_completeness)),
        computed_at=record.computed_at,
        input_hash=record.input_hash,
        bank_notes=tuple(record.bank_notes),
        segment=cast(Segment | None, record.segment),
        scorecard=record.scorecard,
        pd_12m=Decimal(str(record.pd_12m)) if record.pd_12m is not None else None,
        reason_codes=tuple(record.reason_codes or ()),
        ml=_ml_from_json(record.ml) if record.ml is not None else None,
        quality=cast(QualityLevel | None, record.quality),
        quality_reasons=tuple(record.quality_reasons or ()),
    )


def _ml_to_json(ml: MlScore) -> dict[str, Any]:
    return {
        "model_version": ml.model_version,
        "pd_12m": str(ml.pd_12m),
        "score": ml.score,
        "grade": ml.grade,
        "factors": [_factor_to_json(f) for f in ml.factors],
        "reason_codes": list(ml.reason_codes),
    }


def _ml_from_json(raw: dict[str, Any]) -> MlScore:
    return MlScore(
        model_version=raw["model_version"],
        pd_12m=Decimal(raw["pd_12m"]),
        score=raw["score"],
        grade=cast(Grade, raw["grade"]),
        factors=tuple(_factor_from_json(f) for f in raw["factors"]),
        reason_codes=tuple(raw["reason_codes"]),
    )


def _factor_to_json(factor: Factor) -> dict[str, Any]:
    return {
        "code": factor.code,
        "value": factor.value,
        "bin": factor.bin,
        "points": factor.points,
        "direction": factor.direction,
        "client_hint": factor.client_hint,
        "has_data": factor.has_data,
    }


def _factor_from_json(raw: dict[str, Any]) -> Factor:
    return Factor(
        code=raw["code"],
        value=raw["value"],
        bin=raw["bin"],
        points=raw["points"],
        direction=cast(Direction, raw["direction"]),
        client_hint=raw.get("client_hint"),
        has_data=raw.get("has_data", True),
    )
