"""scoring.commands and scoring.events — key: application_id."""

from uuid import UUID

from src.core.messaging import topics
from src.core.messaging.contracts.base import IntegrationMessage


class CalculateScore(IntegrationMessage):
    TYPE = "CalculateScore"
    TOPIC = topics.SCORING_COMMANDS

    application_id: UUID


class ScoreCalculated(IntegrationMessage):
    TYPE = "ScoreCalculated"
    TOPIC = topics.SCORING_EVENTS

    application_id: UUID
    result_id: UUID
    score: int
    risk_grade: str
    flags: list[str] = []


class ScoringFailed(IntegrationMessage):
    TYPE = "ScoringFailed"
    TOPIC = topics.SCORING_EVENTS

    application_id: UUID
    reason: str
