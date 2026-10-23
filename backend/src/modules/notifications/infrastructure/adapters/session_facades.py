from sqlalchemy.ext.asyncio import AsyncSession

from src.core.facades import FacadeRegistry
from src.modules.notifications.application.interfaces.neighbours import FacadeLookup


class SessionFacades(FacadeLookup):
    """Facades bound to one session, for the HTTP handlers and the facade (the
    Kafka handler has `ctx.facade`)."""

    def __init__(self, registry: FacadeRegistry, session: AsyncSession) -> None:
        self._registry = registry
        self._session = session

    def __call__[T](self, key: type[T]) -> T:
        return self._registry.get(key, self._session)
