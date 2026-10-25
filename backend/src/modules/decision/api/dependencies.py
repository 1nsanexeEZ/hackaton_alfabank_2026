from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

from src.core.access.permissions import Permissions
from src.core.access.policies import Policies
from src.core.exceptions.exceptions import NotFoundError, PermissionDeniedError
from src.core.facades import use_facade
from src.core.infrastructure.database.session import DbSession
from src.core.schemas.jwt_dto import OpenSubTokenDTO
from src.modules.applications.facade import ApplicationsFacade
from src.modules.clients.facade import ClientsFacade, OrgPermission
from src.modules.decision.application.input_builder import DecisionInputBuilder
from src.modules.decision.application.policy_versions import (
    InputBuilders,
    PolicyProvider,
    PolicyVersions,
)
from src.modules.decision.domain.policy import CreditPolicy
from src.modules.decision.infrastructure.config_loader import CreditPolicyDocuments
from src.modules.decision.infrastructure.repository import (
    SqlAlchemyDecisionRepository,
    SqlAlchemyFounderPrescreenRepository,
    SqlAlchemyPolicyVersionRepository,
)
from src.modules.enrichment.facade import EnrichmentFacade
from src.modules.products.facade import ProductsFacade
from src.modules.scoring.facade import ScoringFacade


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


def get_policy_versions(request: Request, session: DbSession) -> PolicyVersions:
    return PolicyVersions(
        SqlAlchemyPolicyVersionRepository(session), CreditPolicyDocuments(), request.app.state.clock
    )


def get_decision_history(session: DbSession) -> SqlAlchemyDecisionRepository:
    return SqlAlchemyDecisionRepository(session)


async def get_active_policy(request: Request, session: DbSession) -> CreditPolicy:
    """Active version of the admin or the built-in policy — by the same provider the consumers
    use (`module.wire`)."""
    policies: PolicyProvider = request.app.state.decision_policies
    return await policies.active(SqlAlchemyPolicyVersionRepository(session))


def get_input_builders(
    session: DbSession,
    applications: Annotated[ApplicationsFacade, Depends(use_facade(ApplicationsFacade))],
    enrichment: Annotated[EnrichmentFacade, Depends(use_facade(EnrichmentFacade))],
    scoring: Annotated[ScoringFacade, Depends(use_facade(ScoringFacade))],
    products: Annotated[ProductsFacade, Depends(use_facade(ProductsFacade))],
) -> InputBuilders:
    """The decision input of an application from the neighbours, as `MakeDecision` gathers it."""
    prescreens = SqlAlchemyFounderPrescreenRepository(session)

    def builder(policy: CreditPolicy) -> DecisionInputBuilder:
        return DecisionInputBuilder(policy, applications, enrichment, scoring, products, prescreens)

    return builder


def get_key_rate(request: Request) -> Decimal:
    key_rate: Decimal = request.app.state.settings.key_rate
    return key_rate


PolicyVersionsDep = Annotated[PolicyVersions, Depends(get_policy_versions)]
DecisionHistoryDep = Annotated[SqlAlchemyDecisionRepository, Depends(get_decision_history)]
ActivePolicyDep = Annotated[CreditPolicy, Depends(get_active_policy)]
InputBuildersDep = Annotated[InputBuilders, Depends(get_input_builders)]
KeyRateDep = Annotated[Decimal, Depends(get_key_rate)]
