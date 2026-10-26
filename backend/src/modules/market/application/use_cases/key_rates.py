"""The key rate history: what is in force on a day, the admin adds and removes rates.
Days are Moscow ones: the Bank of Russia's rate takes effect from a Moscow date.

When the rate in force changes, KeyRateChanged goes out (outbox, the same transaction): at once
for a rate from today or earlier and for removing today's rate, and by AnnounceDueKeyRates on the
day a rate entered ahead takes effect. decision recalculates the pre-approved offers on it.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from src.core.domain.clock import Clock
from src.core.domain.moscow import moscow_today
from src.core.messaging.contracts.market import KeyRateChanged
from src.core.uow import UnitOfWork
from src.modules.market.application.dto.key_rates import (
    KeyRateCreate,
    KeyRateDTO,
    KeyRateHistoryDTO,
    KeyRateRecordDTO,
)
from src.modules.market.application.interfaces.outbox import MessageOutbox
from src.modules.market.application.interfaces.repositories import KeyRateRepository
from src.modules.market.domain.enums import RateSource
from src.modules.market.domain.exceptions import (
    KeyRateDateTakenError,
    KeyRateInForceError,
    KeyRateNotFoundError,
)
from src.modules.market.domain.key_rate import CENT, KeyRate


def _current(rate: KeyRate | None, fallback: Decimal) -> KeyRateDTO:
    if rate is None:
        return KeyRateDTO(fallback.quantize(CENT), None, "settings")
    return KeyRateDTO(rate.value, rate.effective_from, rate.source.value)


def _record(rate: KeyRate, today: date, in_force: KeyRate | None) -> KeyRateRecordDTO:
    return KeyRateRecordDTO(
        value=rate.value,
        effective_from=rate.effective_from,
        decided_on=rate.decided_on,
        source=rate.source.value,
        note=rate.note,
        created_at=rate.created_at,
        in_force=in_force is not None and in_force.effective_from == rate.effective_from,
        removable=rate.can_be_removed(today),
    )


async def _announce(
    repository: KeyRateRepository, outbox: MessageOutbox, today: date, fallback: Decimal
) -> None:
    """KeyRateChanged with the rate in force today; key — its date."""
    current = _current(await repository.on(today), fallback)
    await outbox.add(
        KeyRateChanged(value=current.value, effective_from=current.effective_from),
        key=(current.effective_from or today).isoformat(),
        correlation_id=uuid4(),
    )


class GetKeyRateUseCase:
    """Nothing in force on the day (empty history, a first start, tests) — `KEY_RATE`."""

    def __init__(self, repository: KeyRateRepository, clock: Clock, fallback: Decimal) -> None:
        self._repository = repository
        self._clock = clock
        self._fallback = fallback

    async def execute(self, day: date | None = None) -> KeyRateDTO:
        day = day or moscow_today(self._clock)
        return _current(await self._repository.on(day), self._fallback)


class ListKeyRatesUseCase:
    def __init__(self, repository: KeyRateRepository, clock: Clock, fallback: Decimal) -> None:
        self._repository = repository
        self._clock = clock
        self._fallback = fallback

    async def execute(self) -> KeyRateHistoryDTO:
        today = moscow_today(self._clock)
        in_force = await self._repository.on(today)
        items = [_record(rate, today, in_force) for rate in await self._repository.list_all()]
        return KeyRateHistoryDTO(_current(in_force, self._fallback), items)


class AddKeyRateUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        repository: KeyRateRepository,
        outbox: MessageOutbox,
        clock: Clock,
        fallback: Decimal,
    ) -> None:
        self._uow = uow
        self._repository = repository
        self._outbox = outbox
        self._clock = clock
        self._fallback = fallback

    async def execute(self, data: KeyRateCreate, account_id: UUID | None) -> KeyRateRecordDTO:
        rate = KeyRate(
            effective_from=data.effective_from,
            value=data.value,
            source=RateSource.ADMIN,
            decided_on=data.decided_on,
            note=data.note or None,
            created_by=account_id,
            created_at=self._clock.now(),
        )
        today = moscow_today(self._clock)
        async with self._uow:
            if await self._repository.get(rate.effective_from) is not None:
                raise KeyRateDateTakenError()
            await self._repository.add(rate)
            in_force = await self._repository.on(today)
            if rate.effective_from <= today:
                # In force already (or history entered late): announced now, not by the job.
                await self._repository.mark_announced([rate.effective_from], self._clock.now())
                if in_force is not None and in_force.effective_from == rate.effective_from:
                    await _announce(self._repository, self._outbox, today, self._fallback)
            await self._uow.commit()
        return _record(rate, today, in_force)


class RemoveKeyRateUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        repository: KeyRateRepository,
        outbox: MessageOutbox,
        clock: Clock,
        fallback: Decimal,
    ) -> None:
        self._uow = uow
        self._repository = repository
        self._outbox = outbox
        self._clock = clock
        self._fallback = fallback

    async def execute(self, effective_from: date) -> None:
        today = moscow_today(self._clock)
        async with self._uow:
            rate = await self._repository.get(effective_from)
            if rate is None:
                raise KeyRateNotFoundError()
            if not rate.can_be_removed(today):
                raise KeyRateInForceError()
            await self._repository.remove(rate)
            if rate.effective_from == today:
                # Today's rate was in force: the previous one (or the settings) is again.
                await _announce(self._repository, self._outbox, today, self._fallback)
            await self._uow.commit()


class AnnounceDueKeyRatesUseCase:
    """A rate entered ahead takes effect on its date: the market job (hourly) sends
    KeyRateChanged for it once. Returns how many rates were announced."""

    def __init__(
        self,
        uow: UnitOfWork,
        repository: KeyRateRepository,
        outbox: MessageOutbox,
        clock: Clock,
        fallback: Decimal,
    ) -> None:
        self._uow = uow
        self._repository = repository
        self._outbox = outbox
        self._clock = clock
        self._fallback = fallback

    async def execute(self) -> int:
        today = moscow_today(self._clock)
        async with self._uow:
            due = await self._repository.unannounced_until(today)
            if not due:
                return 0
            await self._repository.mark_announced(
                [rate.effective_from for rate in due], self._clock.now()
            )
            await _announce(self._repository, self._outbox, today, self._fallback)
            await self._uow.commit()
        return len(due)
