from typing import Protocol

from src.modules.identity.application.dto.auth import DemoAccountEntryDTO


class DemoAccountCatalog(Protocol):
    """Accounts open for one-click login on a demo stand."""

    def list(self) -> list[DemoAccountEntryDTO]:
        """In display order."""
        ...

    def contains(self, email: str) -> bool: ...
