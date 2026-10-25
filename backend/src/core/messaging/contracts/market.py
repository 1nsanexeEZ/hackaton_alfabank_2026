"""market.events — key: effective_from of the rate (ISO date)."""

from datetime import date
from decimal import Decimal

from src.core.messaging import topics
from src.core.messaging.contracts.base import IntegrationMessage


class KeyRateChanged(IntegrationMessage):
    """The key rate in force changed: a rate from today was entered or removed, or a rate
    entered ahead reached its date. `effective_from` is None — nothing is in force any more,
    the value from the settings is used."""

    TYPE = "KeyRateChanged"
    TOPIC = topics.MARKET_EVENTS

    value: Decimal
    effective_from: date | None = None
