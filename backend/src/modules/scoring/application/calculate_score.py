"""Use case CalculateScore: по команде собрать вход из соседей, посчитать PD-моделью
(сегмент, скоркарта, PD, грейд A–J) и рядом ML-моделью на том же входе, сохранить обе оценки
с input_snapshot и опубликовать результат.

- идемпотентность по event_id команды: повтор возвращает тот же результат и повторно публикует
  ScoreCalculated (causation_id = event_id команды);
- нет снимка обогащения → ScoringFailed (считать не на чем — решит процесс по on_failure);
- признаки клиента — из хранилища на дату заявки (`client_features.py`), признаки заявки — из
  заявки; в `input_snapshot` — оба набора и `feature_snapshot_id`;
- «Данные полные?»: не ответил критичный источник или мало признаков с данными → `quality =
  degraded`; модели всё равно посчитаны (их видит андеррайтер), решение отдаёт заявку человеку;
- scoring ничего не знает про ставки и лимиты и не меняет статусы;
- ScoreCalculated несёт оценку PD-модели и качество данных; ML-оценку decision читает из результата;
- ML-модель не оценивает компанию без выручки (`ml_not_applicable`): в результате — почему.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from src.core.domain.clock import Clock
from src.core.messaging.contracts.scoring import CalculateScore, ScoreCalculated, ScoringFailed
from src.core.messaging.outbox import OutboxWriter
from src.modules.applications.facade import ApplicationsFacade
from src.modules.enrichment.facade import EnrichmentFacade
from src.modules.scoring.application.client_features import ClientFeatureStore
from src.modules.scoring.application.input_builder import build_scoring_input
from src.modules.scoring.application.ports import (
    DataQualityAssessor,
    MlScoringModel,
    ScoringModel,
    ScoringRepository,
)
from src.modules.scoring.application.serialization import dump_input, input_hash
from src.modules.scoring.domain.client_features import FeatureSnapshot
from src.modules.scoring.domain.ml_model import ml_not_applicable
from src.modules.scoring.domain.model import ScoringResult


class CalculateScoreUseCase:
    def __init__(
        self,
        repository: ScoringRepository,
        scorecard: ScoringModel,
        applications: ApplicationsFacade,
        enrichment: EnrichmentFacade,
        clock: Clock,
        ml_model: MlScoringModel | None = None,
        quality: DataQualityAssessor | None = None,
        features: ClientFeatureStore | None = None,
    ) -> None:
        self._repository = repository
        self._scorecard = scorecard
        self._ml_model = ml_model
        self._quality = quality
        self._features = features
        self._applications = applications
        self._enrichment = enrichment
        self._clock = clock

    async def execute(
        self, command: CalculateScore, *, command_event_id: UUID, outbox: OutboxWriter
    ) -> None:
        existing = await self._repository.get_by_command(command_event_id)
        if existing is not None:
            await self._publish_calculated(outbox, existing, command_event_id)
            return

        snapshot = await self._enrichment.get_snapshot(command.application_id)
        if snapshot is None:
            await outbox.add(
                ScoringFailed(
                    application_id=command.application_id, reason="enrichment_snapshot_missing"
                ),
                key=command.application_id,
                correlation_id=command.application_id,
                causation_id=command_event_id,
            )
            return

        application = await self._applications.get_scoring_input(command.application_id)
        stored_features: FeatureSnapshot | None = None
        if self._features is not None:
            scoring_input, stored_features = await self._features.scoring_input(
                application, snapshot
            )
        else:
            scoring_input = build_scoring_input(application, snapshot)
        output = self._scorecard.calculate(scoring_input)
        quality = (
            self._quality.assess(scoring_input.sources_failed, output.data_completeness)
            if self._quality is not None
            else None
        )
        # ML-модель не оценивает заявку вне своей области (нет выручки) — её зоне не верят.
        not_applicable = ml_not_applicable(scoring_input)
        stored = dump_input(scoring_input)
        if stored_features is not None:
            # Откуда признаки клиента; только с хранилищем — старые снимки хешируются, как раньше.
            stored["feature_snapshot_id"] = str(stored_features.id)
        result = ScoringResult(
            id=uuid4(),
            application_id=command.application_id,
            requested_by_command=command_event_id,
            model_version=self._scorecard.version,
            score=output.score,
            grade=output.grade,
            factors=output.factors,
            flags=output.flags,
            data_completeness=output.data_completeness,
            computed_at=self._clock.now(),
            input_hash=input_hash(stored),
            bank_notes=output.bank_notes,
            segment=output.segment,
            scorecard=output.scorecard,
            pd_12m=output.pd_12m,
            reason_codes=output.reason_codes,
            ml=self._ml_model.predict(scoring_input)
            if self._ml_model is not None and not_applicable is None
            else None,
            ml_not_applicable=not_applicable if self._ml_model is not None else None,
            quality=quality.level if quality is not None else None,
            quality_reasons=quality.reasons if quality is not None else (),
        )
        await self._repository.add(result, input_snapshot=stored)
        await self._publish_calculated(outbox, result, command_event_id)

    async def _publish_calculated(
        self, outbox: OutboxWriter, result: ScoringResult, command_event_id: UUID
    ) -> None:
        await outbox.add(
            ScoreCalculated(
                application_id=result.application_id,
                result_id=result.id,
                score=result.score,
                risk_grade=result.grade,
                flags=list(result.flags),
                quality=result.quality,
            ),
            key=result.application_id,
            correlation_id=result.application_id,
            causation_id=command_event_id,
        )
