"""The applications of a company and the client card of one application."""

from uuid import UUID

from src.core.access.access_context import AccessContext
from src.modules.applications.facade import ApplicationCardDTO, ApplicationsFacade
from src.modules.bff.application.dto.applications import (
    ApplicationConsentsDTO,
    ApplicationListDTO,
    ApplicationRowDTO,
    ClientApplicationCardDTO,
    HeadConsentDTO,
    OrganizationRefDTO,
    ProductInfoDTO,
)
from src.modules.bff.application.interfaces.neighbours import Neighbours
from src.modules.bff.application.use_cases.common import ensure_visible
from src.modules.bff.domain.actions import available_actions
from src.modules.bff.domain.client_status import client_status
from src.modules.clients.facade import ClientsFacade
from src.modules.decision.facade import ClientDecisionDTO, DecisionFacade
from src.modules.identity.facade import IdentityFacade
from src.modules.notifications.facade import FeedItemDTO, NotificationsFacade
from src.modules.products.facade import ProductsFacade
from src.modules.projector.facade import ProjectorFacade, TimelineEntryDTO

CARD_FEED = 10


class ListApplicationsUseCase:
    def __init__(self, neighbours: Neighbours) -> None:
        self._n = neighbours

    async def execute(
        self,
        access: AccessContext,
        organization_id: UUID,
        status: str | None,
        limit: int,
        offset: int,
    ) -> ApplicationListDTO:
        await ensure_visible(self._n, access, organization_id)
        page = await self._n(ProjectorFacade).list_applications(
            organization_id, status, limit, offset
        )
        return ApplicationListDTO(
            items=tuple(ApplicationRowDTO.of(r) for r in page.items), total=page.total
        )


class ApplicationCardUseCase:
    """The card and its status come from applications, not from the projection."""

    def __init__(self, neighbours: Neighbours) -> None:
        self._n = neighbours

    async def execute(
        self, access: AccessContext, application_id: UUID
    ) -> ClientApplicationCardDTO:
        account_id = access.user_id
        card = await self._n(ApplicationsFacade).get_card(application_id)
        await ensure_visible(self._n, access, card.organization_id)
        permissions = await self._n(ClientsFacade).get_member_permissions(
            account_id, card.organization_id
        )

        async def product_name() -> str | None:
            return (await self._n(ProductsFacade).get_product(card.product_code)).name

        name = await self._n.optional("product", product_name, None)
        timeline: list[TimelineEntryDTO] = await self._n.optional(
            "timeline",
            lambda: self._n(ProjectorFacade).get_timeline(application_id, "client"),
            [],
        )
        decision = await self._n.optional(
            "decision", lambda: self._n(DecisionFacade).get_client_view(application_id), None
        )
        feed: list[FeedItemDTO] = await self._n.optional(
            "feed",
            lambda: self._n(NotificationsFacade).latest(
                account_id, card.organization_id, application_id, CARD_FEED
            ),
            [],
        )
        head_consent = await self._n.optional(
            "head_consent", lambda: self._head_consent(card.organization_id), None
        )
        return _card(
            card, name, timeline, decision, head_consent, feed, permissions, self._n.degraded
        )

    async def _head_consent(self, organization_id: UUID) -> HeadConsentDTO | None:
        """The head's name is the registry's; a head without an account in the company
        has not given the consent."""
        head_name = (await self._n(ClientsFacade).get_snapshot(organization_id)).head_name
        if head_name is None:
            return None
        head_id = await self._n(ClientsFacade).get_registry_head(organization_id)
        consent = None
        if head_id is not None:
            consent = await self._n(IdentityFacade).get_active_consent(
                head_id, "credit_bureau_personal"
            )
        return HeadConsentDTO(
            required=True,
            given=consent is not None,
            given_at=consent.given_at if consent else None,
            head_name=head_name,
        )


def _card(
    card: ApplicationCardDTO,
    product_name: str | None,
    timeline: list[TimelineEntryDTO],
    decision: ClientDecisionDTO | None,
    head_consent: HeadConsentDTO | None,
    feed: list[FeedItemDTO],
    permissions: frozenset[str],
    degraded: tuple[str, ...],
) -> ClientApplicationCardDTO:
    terms = card.product_terms
    org = card.org_snapshot
    # The decision module is not reachable: the summary kept in the card is
    # the same client-safe text, without terms.
    client_decision = decision if decision is not None else card.decision_summary
    return ClientApplicationCardDTO(
        id=card.id,
        number=card.number,
        organization=OrganizationRefDTO(id=org.id, name=org.name, inn=org.inn) if org else None,
        product=ProductInfoDTO(
            code=terms.code,
            name=product_name,
            amount_min=terms.amount_min,
            amount_max=terms.amount_max,
            term_min_months=terms.term_min_months,
            term_max_months=terms.term_max_months,
            rate_base=terms.rate_base,
            rate_max=terms.rate_max,
        ),
        status=card.status,
        client_status=client_status(
            card.status, card.client_stage, card.offer.kind if card.offer else None
        ),
        client_stage=card.client_stage,
        request=card.request,
        product_fields=dict(card.product_fields),
        collateral=card.collateral,
        documents=tuple(card.documents),
        info_request=next((r for r in card.info_requests if r.status == "open"), None),
        offer=card.offer,
        decision=client_decision,
        consents=ApplicationConsentsDTO(head_credit_bureau=head_consent),
        timeline=tuple(e for e in timeline if e.audience == "client"),
        feed=tuple(feed),
        available_actions=tuple(available_actions(card.status, permissions)),
        my_permissions=tuple(sorted(permissions)),
        created_at=card.created_at,
        updated_at=card.updated_at,
        submitted_at=card.submitted_at,
        closed_at=card.closed_at,
        degraded=degraded,
    )
