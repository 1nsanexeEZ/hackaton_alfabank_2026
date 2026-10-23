"""Overdue offers go to EXPIRED.

Runs outside a Kafka handler: every application in a transaction of its own,
so a client accepting at the same moment only makes us skip that one."""

from src.core.domain.clock import Clock
from src.modules.applications.application.interfaces.transactions import (
    ApplicationTransactions,
    StaleApplicationError,
)
from src.modules.applications.application.use_cases.commands import ExpireOfferUseCase


class ExpireOffersUseCase:
    def __init__(self, transactions: ApplicationTransactions, clock: Clock) -> None:
        self._transactions = transactions
        self._clock = clock

    async def execute(self, batch_size: int = 100) -> int:
        """How many offers expired."""
        async with self._transactions() as transaction:
            due = await transaction.applications.offers_expired_by(self._clock.now(), batch_size)
        expired = 0
        for application_id in due:
            try:
                async with self._transactions() as transaction:
                    expire = ExpireOfferUseCase(
                        transaction.applications, transaction.outbox, self._clock
                    )
                    if await expire.execute(application_id):
                        await transaction.commit()
                        expired += 1
            except StaleApplicationError:
                continue
        return expired
