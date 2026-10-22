"""Use case CalculateScore: по команде собрать вход из соседей, посчитать PD-моделью
(сегмент, скоркарта, PD, грейд A–J), сохранить с input_snapshot и опубликовать результат.

- идемпотентность по event_id команды: повтор возвращает тот же результат и повторно публикует
  ScoreCalculated (causation_id = event_id команды);
- нет снимка обогащения → ScoringFailed (считать не на чем — решит процесс по on_failure);
- scoring ничего не знает про ставки и лимиты и не меняет статусы.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from src.core.domain.clock import Clock
from src.core.messaging.contracts.scoring import CalculateScore, ScoreCalculated, ScoringFailed
from src.core.messaging.outbox import OutboxWriter
from src.modules.applications.facade import ApplicationsFacade
from src.modules.enrichment.facade import EnrichmentFacade
from src.modules.scoring.application.input_builder import build_scoring_input
from src.modules.scoring.application.ports import ScoringModel, ScoringRepository
from src.modules.scoring.application.serialization import dump_input, input_hash
from src.modules.scoring.domain.model import ScoringResult


class CalculateScoreUseCase:
    def __init__(
        self,
        repository: ScoringRepository,
        scorecard: ScoringModel,
        applications: ApplicationsFacade,
        enrichment: EnrichmentFacade,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._scorecard = scorecard
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
        scoring_input = build_scoring_input(application, snapshot)
        output = self._scorecard.calculate(scoring_input)
        stored = dump_input(scoring_input)
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
            ),
            key=result.application_id,
            correlation_id=result.application_id,
            causation_id=command_event_id,
        )
