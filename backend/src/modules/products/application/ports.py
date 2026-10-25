from decimal import Decimal
from typing import Protocol

from src.modules.products.domain.product import CreditProduct


class ProductRepository(Protocol):
    async def get_current(self, code: str) -> CreditProduct | None:
        """The published version of the product: the latest active one, else
        the latest archived one. Drafts are never current."""
        ...

    async def get_version(self, code: str, version: int) -> CreditProduct | None: ...

    async def get_latest(self, code: str) -> CreditProduct | None:
        """The latest version whatever its status: the one the catalog changes."""
        ...

    async def list_active(self) -> list[CreditProduct]:
        """Catalog order; one (the latest) version per code."""
        ...

    async def list_latest(self) -> list[CreditProduct]:
        """Catalog order; the latest version of every code, drafts and archived too."""
        ...

    async def save(self, product: CreditProduct) -> None:
        """Insert or update by code and version; the caller commits. A version
        saved by someone else in the meantime is a ConflictError."""
        ...

    async def delete(self, product: CreditProduct) -> None:
        """Only a draft: nothing refers to it yet."""
        ...


class KeyRates(Protocol):
    async def current(self) -> Decimal:
        """The key rate in force today, % a year (the market module)."""
        ...
