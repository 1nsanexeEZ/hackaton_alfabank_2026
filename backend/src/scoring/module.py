"""Wiring of the scoring module into the application."""

from __future__ import annotations

from fastapi import FastAPI

from src.applications.facade import ApplicationsFacade
from src.core.messaging import topics
from src.core.messaging.contracts.scoring import CalculateScore
from src.core.messaging.subscriber import HandlerContext, Subscription
from src.enrichment.facade import EnrichmentFacade
from src.scoring.application.calculate_score import CalculateScoreUseCase
from src.scoring.domain.scorecard import Scorecard
from src.scoring.facade import ScoringFacade
from src.scoring.infrastructure.config_loader import default_scorecard
from src.scoring.infrastructure.facade_impl import ScoringFacadeImpl
from src.scoring.infrastructure.repository import SqlAlchemyScoringRepository

NAME = "scoring"

# Карта грузится один раз на процесс; невалидный YAML → исключение при старте.
_scorecard: Scorecard | None = None


def register(app: FastAPI) -> None:
    """Scoring has no public HTTP API — only a facade and a command handler."""


def wire(app: FastAPI) -> None:
    global _scorecard
    _scorecard = default_scorecard()
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
