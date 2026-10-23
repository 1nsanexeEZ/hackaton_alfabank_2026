from collections.abc import Callable
from typing import Protocol

from src.core.uow import UnitOfWork
from src.modules.projector.application.interfaces.neighbours import FacadeLookup
from src.modules.projector.application.interfaces.repositories import ReadModelStore


class ProjectionTransaction(UnitOfWork, Protocol):
    """A unit of work on a session of its own, for the projection outside a
    Kafka handler (the rebuild): entering opens the session, leaving rolls back
    what was not committed and closes it. The store and the neighbours'
    facades are bound to that session."""

    @property
    def store(self) -> ReadModelStore: ...

    @property
    def facades(self) -> FacadeLookup: ...


# A new transaction per call: the rebuild runs every step in its own.
ProjectionTransactions = Callable[[], ProjectionTransaction]
