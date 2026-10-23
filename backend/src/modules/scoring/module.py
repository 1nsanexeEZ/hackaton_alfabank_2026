"""Wiring of the scoring module into the application."""

from __future__ import annotations

from fastapi import FastAPI

from src.core.messaging import topics
from src.core.messaging.contracts.scoring import CalculateScore
from src.core.messaging.subscriber import HandlerContext, Subscription
from src.modules.applications.facade import ApplicationsFacade
from src.modules.enrichment.facade import EnrichmentFacade
from src.modules.scoring.application.calculate_score import CalculateScoreUseCase
from src.modules.scoring.application.ports import MlScoringModel, ScoringModel
from src.modules.scoring.facade import ScoringFacade
from src.modules.scoring.infrastructure.config_loader import default_model
from src.modules.scoring.infrastructure.facade_impl import ScoringFacadeImpl
from src.modules.scoring.infrastructure.ml_loader import default_ml_model
from src.modules.scoring.infrastructure.repository import SqlAlchemyScoringRepository

NAME = "scoring"

# Модели грузятся один раз на процесс; невалидный YAML → исключение при старте.
_scorecard: ScoringModel | None = None
_ml_model: MlScoringModel | None = None


def register(app: FastAPI) -> None:
    """Scoring has no public HTTP API — only a facade and a command handler."""


def wire(app: FastAPI) -> None:
    global _scorecard, _ml_model
    _scorecard = default_model()
    _ml_model = default_ml_model()
    scorecard = _scorecard
    app.state.facades.register(ScoringFacade, lambda session: ScoringFacadeImpl(session, scorecard))


async def _on_calculate_score(ctx: HandlerContext, payload: CalculateScore) -> None:
    if _scorecard is None:
        raise RuntimeError("scoring module is not wired")
    use_case = CalculateScoreUseCase(
        SqlAlchemyScoringRepository(ctx.session),
        _scorecard,
        ctx.facade(ApplicationsFacade),
        ctx.facade(EnrichmentFacade),
        ctx.clock,
        _ml_model,
    )
    await use_case.execute(payload, command_event_id=ctx.envelope.event_id, outbox=ctx.outbox)


def subscribers() -> list[Subscription]:
    return [
        Subscription(
            module=NAME,
            topic=topics.SCORING_COMMANDS,
            group_id="scoring.commands",
            handler=_on_calculate_score,
            message_types=frozenset({CalculateScore.TYPE}),
        )
    ]
