"""Processes waiting for a reply too long go down their timeout branch.

Runs outside a Kafka handler: every application in a transaction of its own."""

from datetime import timedelta

from src.core.domain.clock import Clock
from src.modules.process.application.interfaces.transactions import (
    ProcessTransactions,
    StaleProcessError,
)
from src.modules.process.application.use_cases.processes import TimeOutProcessUseCase


class TimeOutStuckStepsUseCase:
    def __init__(self, transactions: ProcessTransactions, clock: Clock) -> None:
        self._transactions = transactions
        self._clock = clock

    async def execute(
        self, min_wait: timedelta = timedelta(seconds=30), batch_size: int = 100
    ) -> int:
        """How many processes went down the timeout branch."""
        async with self._transactions() as transaction:
            candidates = await transaction.processes.waiting_for_replies_since(
                self._clock.now() - min_wait, batch_size
            )
        timed_out = 0
        for application_id in candidates:
            try:
                async with self._transactions() as transaction:
                    time_out = TimeOutProcessUseCase(
                        transaction.processes,
                        transaction.tasks,
                        transaction.outbox,
                        transaction.facts,
                        self._clock,
                    )
                    if await time_out.execute(application_id):
                        await transaction.commit()
                        timed_out += 1
            except StaleProcessError:
                # The reply came in between: the process is no longer stuck.
                continue
        return timed_out
