from typing import Protocol


class FacadeLookup(Protocol):
    """Facades of other modules bound to the current transaction (`ctx.facade`).
    An unregistered facade raises a LookupError (FacadeNotRegisteredError)."""

    def __call__[T](self, key: type[T]) -> T: ...
