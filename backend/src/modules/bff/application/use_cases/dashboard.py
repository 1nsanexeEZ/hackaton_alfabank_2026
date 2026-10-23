"""The main screen of the client: their companies and, for the chosen one, the
counters, active applications, what waits for the client, the pre-approval or
the founder's prescreen, the feed and the news."""

from dataclasses import asdict
from uuid import UUID

from src.core.access.access_context import AccessContext
from src.core.exceptions.exceptions import NotFoundError
from src.modules.applications.facade import ACTIVE_STATUSES
from src.modules.bff.application.dto.applications import ApplicationRowDTO
from src.modules.bff.application.dto.dashboard import (
    DashboardDTO,
    FeedDTO,
    PreApprovedProductDTO,
    StartupBlockDTO,
    TodoItemDTO,
)
from src.modules.bff.application.dto.organizations import (
    CurrentOrganizationDTO,
    OrganizationBriefDTO,
)
from src.modules.bff.application.interfaces.neighbours import Neighbours
from src.modules.bff.application.use_cases.common import ensure_visible, segment_of
from src.modules.bff.domain.actions import CONSENT_PENDING_STATUSES, consent_todo, todo_for
from src.modules.clients.facade import ClientsFacade
from src.modules.decision.facade import DecisionFacade
from src.modules.identity.facade import IdentityFacade
from src.modules.notifications.facade import NewsItemDTO, NotificationsFacade
from src.modules.products.facade import ProductsFacade
from src.modules.projector.facade import ProjectorFacade

DASHBOARD_APPLICATIONS = 5
DASHBOARD_FEED = 5
DASHBOARD_NEWS = 5
# The projector filters by one status; active rows are picked from the latest ones.
_RECENT_ROWS = 50


class DashboardUseCase:
    def __init__(self, neighbours: Neighbours) -> None:
        self._n = neighbours

    async def execute(self, access: AccessContext, organization_id: UUID | None) -> DashboardDTO:
        """Without organization_id — the first company."""
        account_id = access.user_id
        organizations = await self._n(ClientsFacade).list_my_organizations(account_id)
        briefs = tuple(OrganizationBriefDTO.of(o) for o in organizations)
        if organization_id is None and not organizations:
            return DashboardDTO(
                onboarding=True,
                organization=None,
                organizations=(),
                counters=None,
                pre_approved=(),
                active_applications=(),
                todo=(),
                feed=FeedDTO(unread=0, items=()),
                news=(),
                degraded=self._n.degraded,
            )
        chosen = organization_id or organizations[0].id
        await ensure_visible(self._n, access, chosen)
        summary = next((o for o in organizations if o.id == chosen), None)
        if summary is None:
            raise NotFoundError("Organization not found")
        snapshot = await self._n(ClientsFacade).get_snapshot(chosen)

        projector = self._n(ProjectorFacade)
        counters = await projector.get_organization_dashboard(chosen)
        recent = await projector.list_applications(chosen, limit=_RECENT_ROWS)
        active = [r for r in recent.items if r.status in ACTIVE_STATUSES]
        todo = []
        for row in active:
            found = todo_for(row.action_required, row.number)
            if found is not None:
                kind, title = found
                todo.append(
                    TodoItemDTO(
                        application_id=row.application_id, number=row.number, kind=kind, title=title
                    )
                )
        pending = next((r for r in active if r.status in CONSENT_PENDING_STATUSES), None)
        if pending is not None and await self._n.optional(
            "head_consent", lambda: self._head_consent_missing(account_id, chosen), False
        ):
            kind, title = consent_todo(pending.number)
            todo.append(
                TodoItemDTO(
                    application_id=pending.application_id,
                    number=pending.number,
                    kind=kind,
                    title=title,
                )
            )

        segment = segment_of(snapshot)
        startup = None
        if segment == "startup":
            pre_approved: tuple[PreApprovedProductDTO, ...] = ()
            prescreen = await self._n.optional(
                "prescreen",
                lambda: self._n(DecisionFacade).get_founder_prescreen(chosen),
                None,
            )
            startup = StartupBlockDTO(prescreen=prescreen)
        else:
            pre_approved = await self._n.optional(
                "pre_approved", lambda: self._pre_approved(chosen), ()
            )
        feed = await self._n.optional(
            "feed", lambda: self._feed(account_id, chosen), FeedDTO(unread=0, items=())
        )
        news: list[NewsItemDTO] = await self._n.optional(
            "news",
            lambda: self._n(NotificationsFacade).personal_news(chosen, DASHBOARD_NEWS),
            [],
        )
        return DashboardDTO(
            onboarding=False,
            organization=CurrentOrganizationDTO(
                **asdict(OrganizationBriefDTO.of(summary)),
                verification_status=snapshot.verification_status,
                registry_status=snapshot.registry_status,
                segment=segment,
            ),
            organizations=briefs,
            counters=counters,
            pre_approved=pre_approved,
            active_applications=tuple(
                ApplicationRowDTO.of(r) for r in active[:DASHBOARD_APPLICATIONS]
            ),
            todo=tuple(todo),
            feed=feed,
            news=tuple(news),
            degraded=self._n.degraded,
            startup=startup,
        )

    async def _pre_approved(self, organization_id: UUID) -> tuple[PreApprovedProductDTO, ...]:
        offers = await self._n(DecisionFacade).get_pre_approved(organization_id)
        if not offers:
            return ()
        names = await self._product_names()
        return tuple(
            PreApprovedProductDTO(
                product_code=o.product_code,
                product_name=names.get(o.product_code),
                max_amount=o.max_amount,
                rate_from=o.rate_from,
                term_max_months=o.term_max_months,
                valid_until=o.valid_until,
            )
            for o in offers
        )

    async def _head_consent_missing(self, account_id: UUID, organization_id: UUID) -> bool:
        if await self._n(ClientsFacade).get_registry_head(organization_id) != account_id:
            return False
        consent = await self._n(IdentityFacade).get_active_consent(
            account_id, "credit_bureau_personal"
        )
        return consent is None

    async def _product_names(self) -> dict[str, str]:
        async def load() -> dict[str, str]:
            return {p.code: p.name for p in await self._n(ProductsFacade).list_active()}

        return await self._n.optional("products", load, {})

    async def _feed(self, account_id: UUID, organization_id: UUID) -> FeedDTO:
        notifications = self._n(NotificationsFacade)
        unread = await notifications.unread_count(account_id, organization_id)
        items = await notifications.latest(account_id, organization_id, limit=DASHBOARD_FEED)
        return FeedDTO(unread=unread, items=tuple(items))
