from collections.abc import Callable
from typing import Protocol

from src.core.uow import UnitOfWork
from src.modules.applications.application.interfaces.outbox import MessageOutbox
from src.modules.applications.application.interfaces.repositories import ApplicationRepository


class StaleApplicationError(Exception):
    """The application was changed by another transaction after it was read."""


class ApplicationTransaction(UnitOfWork, Protocol):
    """A unit of work on a session of its own, for code outside a request and
    a Kafka handler (the offer expiry job): entering opens the session, leaving
    rolls back what was not committed and closes it. The repository and the
    outbox are bound to that session. A concurrent change of the application
    leaves the block as StaleApplicationError."""

    @property
    def applications(self) -> ApplicationRepository: ...

    @property
    def outbox(self) -> MessageOutbox: ...


# A new transaction per call: the expiry job runs every application in its own.
ApplicationTransactions = Callable[[], ApplicationTransaction]
