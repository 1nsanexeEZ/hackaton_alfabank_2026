from collections.abc import Callable
from typing import Protocol

from src.core.uow import UnitOfWork
from src.modules.process.application.interfaces.outbox import MessageOutbox
from src.modules.process.application.interfaces.repositories import (
    ProcessRepository,
    TaskRepository,
)
from src.modules.process.domain.steps import ProcessFacts


class StaleProcessError(Exception):
    """The process was changed by another transaction after it was read."""


class ProcessTransaction(UnitOfWork, Protocol):
    """A unit of work on a session of its own, for the engine outside a Kafka
    handler and a request (the timeout job): entering opens the session,
    leaving rolls back what was not committed and closes it. The repositories,
    the outbox and the facts are bound to that session. A concurrent change of
    the process leaves the block as StaleProcessError."""

    @property
    def processes(self) -> ProcessRepository: ...

    @property
    def tasks(self) -> TaskRepository: ...

    @property
    def outbox(self) -> MessageOutbox: ...

    @property
    def facts(self) -> ProcessFacts: ...


# A new transaction per call: the timeout job runs every application in its own.
ProcessTransactions = Callable[[], ProcessTransaction]
