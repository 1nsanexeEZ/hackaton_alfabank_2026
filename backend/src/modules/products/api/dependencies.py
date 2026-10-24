from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

from src.core.access.permissions import Permissions
from src.core.access.policies import Policies
from src.core.exceptions.exceptions import NotFoundError, PermissionDeniedError
from src.core.facades import get_facade_registry, use_facade
from src.core.infrastructure.database.session import DbSession
from src.core.schemas.jwt_dto import OpenSubTokenDTO
from src.modules.clients.facade import ClientsFacade, OrgPermission
from src.modules.process.facade import ProcessFacade
from src.modules.products.application.borrowers import BorrowerProfiles
from src.modules.products.application.catalog import ProductCatalog
from src.modules.products.application.services import ProductService
from src.modules.products.infrastructure.facade_impl import borrower_profiles
from src.modules.products.infrastructure.repository import SqlAlchemyProductRepository


def get_product_service(session: DbSession) -> ProductService:
    return ProductService(SqlAlchemyProductRepository(session))


def get_product_catalog(
    session: DbSession, process: Annotated[ProcessFacade, Depends(use_facade(ProcessFacade))]
) -> ProductCatalog:
    return ProductCatalog(SqlAlchemyProductRepository(session), process.workflow_codes())


def get_borrower_profiles(request: Request, session: DbSession) -> BorrowerProfiles:
    return borrower_profiles(get_facade_registry(request), session)


ProductServiceDep = Annotated[ProductService, Depends(get_product_service)]
ProductCatalogDep = Annotated[ProductCatalog, Depends(get_product_catalog)]
BorrowerProfilesDep = Annotated[BorrowerProfiles, Depends(get_borrower_profiles)]


def sees_every_organization(token: OpenSubTokenDTO) -> bool:
    """Admin and bank staff: `organizations.read` without the `org_member` policy."""
    if Permissions.ADMIN.value in token.permissions:
        return True
    permission = Permissions.ORGANIZATIONS_READ.value
    return permission in token.permissions and Policies.ORG_MEMBER.value not in (
        token.policies.get(permission, ())
    )


async def ensure_can_view(
    token: OpenSubTokenDTO, organization_id: UUID, clients: ClientsFacade
) -> None:
    """A client sees only its companies; a stranger gets 404, not 403."""
    if sees_every_organization(token):
        return
    try:
        await clients.ensure_can(token.subject, organization_id, OrgPermission.VIEW)
    except PermissionDeniedError:
        raise NotFoundError("Organization not found") from None
