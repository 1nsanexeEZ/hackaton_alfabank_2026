from typing import Protocol

from src.modules.products.domain.product import CreditProduct


class ProductRepository(Protocol):
    async def get_current(self, code: str) -> CreditProduct | None:
        """The published version of the product: the latest active one, else
        the latest archived one. Drafts are never current."""
        ...

    async def get_version(self, code: str, version: int) -> CreditProduct | None: ...

    async def list_active(self) -> list[CreditProduct]:
        """Catalog order; one (the latest) version per code."""
        ...

    async def save(self, product: CreditProduct) -> None:
        """Insert or update by code and version; the caller commits."""
        ...
