"""Keeping the catalog: the bank adds products, changes their terms and takes
them off sale. Applications keep a copy of the terms they were opened with, so
none of this changes an application already in progress."""

from collections.abc import Collection
from dataclasses import replace

from src.core.exceptions.exceptions import ConflictError, NotFoundError
from src.modules.products.application.ports import ProductRepository
from src.modules.products.domain.product import CreditProduct, ProductStatus
from src.modules.products.domain.value_objects import invalid


class ProductCatalog:
    """The version, the status and the catalog position belong to the catalog:
    whatever a given product carries in them is replaced."""

    def __init__(self, products: ProductRepository, workflow_codes: Collection[str]) -> None:
        self._products = products
        self._workflow_codes = frozenset(workflow_codes)

    async def list_all(self) -> list[CreditProduct]:
        """Every product in its latest version, drafts and archived ones too."""
        return await self._products.list_latest()

    async def create(self, product: CreditProduct, *, publish: bool) -> CreditProduct:
        """Version 1 at the end of the catalog: a draft, or active right away."""
        catalog = await self._products.list_latest()
        if any(p.code == product.code for p in catalog):
            raise ConflictError("Product already exists", details={"code": product.code.value})
        self._check(product, catalog)
        created = replace(
            product,
            version=1,
            status=ProductStatus.ACTIVE if publish else ProductStatus.DRAFT,
            sort_order=max((p.sort_order for p in catalog), default=0) + 1,
        )
        await self._products.save(created)
        return created

    async def update(self, product: CreditProduct) -> CreditProduct:
        """New terms. A draft is changed in place. A published product gets a new
        active version, and the previous one goes to the archive; an archived
        product comes back to the catalog this way."""
        latest = await self._latest(product.code.value)
        self._check(product, await self._products.list_latest())
        if latest.status == ProductStatus.DRAFT:
            revised = replace(
                product, version=latest.version, status=latest.status, sort_order=latest.sort_order
            )
        else:
            revised = replace(
                product,
                version=latest.version + 1,
                status=ProductStatus.ACTIVE,
                sort_order=latest.sort_order,
            )
            if latest.is_selectable:
                latest.archive()
                await self._products.save(latest)
        await self._products.save(revised)
        return revised

    async def activate(self, code: str) -> CreditProduct:
        """Publish a draft; anything else is `409 invalid_transition`."""
        product = await self._latest(code)
        product.activate()
        await self._products.save(product)
        return product

    async def remove(self, code: str) -> None:
        """A draft is deleted: nothing refers to it yet. A published product goes
        to the archive: old applications refer to it. Archived — `409`."""
        product = await self._latest(code)
        if product.status == ProductStatus.DRAFT:
            await self._products.delete(product)
            return
        product.archive()
        await self._products.save(product)

    async def _latest(self, code: str) -> CreditProduct:
        product = await self._products.get_latest(code)
        if product is None:
            raise NotFoundError("Product not found", details={"code": code})
        return product

    def _check(self, product: CreditProduct, catalog: list[CreditProduct]) -> None:
        """What the product refers to outside itself: a route of the process
        module and a card of the frontend catalog."""
        if product.processing.workflow_code not in self._workflow_codes:
            raise invalid("workflow_code", "unknown", "No such route in the process module")
        if any(p.frontend_id == product.frontend_id and p.code != product.code for p in catalog):
            raise invalid("frontend_id", "taken", "Another product has this frontend id")
