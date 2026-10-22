"""Client screens: dashboard, applications list, application card, product
matching, calculator with the pre-approval.

Lists and counters come from the projector; the card and the status of one
application always come from applications, the source of truth, so the client
sees the result of an action right away. Access to the company is checked
before anything is read: the projector has no checks of its own."""

from decimal import Decimal
from uuid import UUID

from src.core.exceptions.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from src.modules.applications.facade import ACTIVE_STATUSES, ApplicationCardDTO, ApplicationsFacade
from src.modules.bff.application import views
from src.modules.bff.application.actions import available_actions, todo_for
from src.modules.bff.application.client_status import client_status, offer_kind_of_row
from src.modules.bff.application.neighbours import Neighbours
from src.modules.clients.facade import ClientsFacade, OrganizationSummaryDTO, OrgPermission
from src.modules.decision.facade import ClientDecisionDTO, DecisionFacade, PreApprovedOfferDTO
from src.modules.notifications.facade import FeedItemDTO, NotificationsFacade
from src.modules.products.facade import ProductDTO, ProductsFacade, Purpose, Repayment
from src.modules.projector.facade import ApplicationOverviewDTO, ProjectorFacade, TimelineEntryDTO

DASHBOARD_APPLICATIONS = 5
DASHBOARD_FEED = 5
DASHBOARD_NEWS = 5
CARD_FEED = 10
# The projector filters by one status; active rows are picked from the latest ones.
_RECENT_ROWS = 50


class ClientScreens:
    def __init__(self, neighbours: Neighbours) -> None:
        self._n = neighbours

    # --- access -------------------------------------------------------------

    async def _ensure_visible(
        self, account_id: UUID, member_of: frozenset[UUID] | None, organization_id: UUID
    ) -> None:
        """A stranger's company is 404: its existence is not disclosed."""
        if member_of is not None and organization_id not in member_of:
            raise NotFoundError("Organization not found")
        try:
            await self._n(ClientsFacade).ensure_can(account_id, organization_id, OrgPermission.VIEW)
        except PermissionDeniedError:
            raise NotFoundError("Organization not found") from None

    # --- dashboard ----------------------------------------------------------

    async def dashboard(
        self, account_id: UUID, member_of: frozenset[UUID] | None, organization_id: UUID | None
    ) -> views.Dashboard:
        organizations = await self._n(ClientsFacade).list_my_organizations(account_id)
        briefs = [_brief(o) for o in organizations]
        if organization_id is None and not organizations:
            return views.Dashboard(
                onboarding=True,
                organization=None,
                organizations=[],
                counters=None,
                pre_approved=[],
                active_applications=[],
                todo=[],
                feed=views.Feed(unread=0, items=[]),
                news=[],
                degraded=self._n.degraded,
            )
        chosen = organization_id or organizations[0].id
        await self._ensure_visible(account_id, member_of, chosen)
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
                    views.TodoItem(
                        application_id=row.application_id, number=row.number, kind=kind, title=title
                    )
                )

        pre_approved = await self._n.optional(
            "pre_approved", lambda: self._pre_approved(chosen), []
        )
        feed = await self._n.optional(
            "feed", lambda: self._feed(account_id, chosen), views.Feed(unread=0, items=[])
        )
        news = await self._n.optional(
            "news",
            lambda: self._n(NotificationsFacade).personal_news(chosen, DASHBOARD_NEWS),
            [],
        )
        return views.Dashboard(
            onboarding=False,
            organization=views.CurrentOrganization(
                **_brief(summary).model_dump(),
                verification_status=snapshot.verification_status,
                registry_status=snapshot.registry_status,
            ),
            organizations=briefs,
            counters=views.Counters.model_validate(counters) if counters else None,
            pre_approved=pre_approved,
            active_applications=[_row(r) for r in active[:DASHBOARD_APPLICATIONS]],
            todo=todo,
            feed=feed,
            news=[views.NewsItem.model_validate(n) for n in news],
            degraded=self._n.degraded,
        )

    async def _pre_approved(self, organization_id: UUID) -> list[views.PreApprovedOffer]:
        offers = await self._n(DecisionFacade).get_pre_approved(organization_id)
        if not offers:
            return []
        names = await self._product_names()
        return [
            views.PreApprovedOffer(
                product_code=o.product_code,
                product_name=names.get(o.product_code),
                max_amount=o.max_amount,
                rate_from=o.rate_from,
                term_max_months=o.term_max_months,
                valid_until=o.valid_until,
            )
            for o in offers
        ]

    async def _product_names(self) -> dict[str, str]:
        async def load() -> dict[str, str]:
            return {p.code: p.name for p in await self._n(ProductsFacade).list_active()}

        return await self._n.optional("products", load, {})

    async def _feed(self, account_id: UUID, organization_id: UUID) -> views.Feed:
        notifications = self._n(NotificationsFacade)
        unread = await notifications.unread_count(account_id, organization_id)
        items = await notifications.latest(account_id, organization_id, limit=DASHBOARD_FEED)
        return views.Feed(unread=unread, items=[views.FeedItem.model_validate(i) for i in items])

    # --- applications list --------------------------------------------------

    async def applications(
        self,
        account_id: UUID,
        member_of: frozenset[UUID] | None,
        organization_id: UUID,
        status: str | None,
        limit: int,
        offset: int,
    ) -> views.ApplicationList:
        await self._ensure_visible(account_id, member_of, organization_id)
        page = await self._n(ProjectorFacade).list_applications(
            organization_id, status, limit, offset
        )
        return views.ApplicationList(items=[_row(r) for r in page.items], total=page.total)

    # --- application card ---------------------------------------------------

    async def application(
        self, account_id: UUID, member_of: frozenset[UUID] | None, application_id: UUID
    ) -> views.ClientApplicationCard:
        card = await self._n(ApplicationsFacade).get_card(application_id)
        await self._ensure_visible(account_id, member_of, card.organization_id)
        permissions = await self._n(ClientsFacade).get_member_permissions(
            account_id, card.organization_id
        )

        async def product_name() -> str | None:
            return (await self._n(ProductsFacade).get_product(card.product_code)).name

        name = await self._n.optional("product", product_name, None)
        timeline = await self._n.optional(
            "timeline",
            lambda: self._n(ProjectorFacade).get_timeline(application_id, "client"),
            [],
        )
        decision = await self._n.optional(
            "decision", lambda: self._n(DecisionFacade).get_client_view(application_id), None
        )
        feed = await self._n.optional(
            "feed",
            lambda: self._n(NotificationsFacade).latest(
                account_id, card.organization_id, application_id, CARD_FEED
            ),
            [],
        )
        return _card(card, name, timeline, decision, feed, permissions, self._n.degraded)

    # --- product matching ---------------------------------------------------

    async def recommendations(
        self,
        account_id: UUID,
        member_of: frozenset[UUID] | None,
        organization_id: UUID | None,
        purpose: Purpose,
        amount: Decimal,
        term_months: int,
    ) -> views.Recommendations:
        pre_approved: dict[str, Decimal] = {}
        if organization_id is not None:
            await self._ensure_visible(account_id, member_of, organization_id)

            async def load() -> dict[str, Decimal]:
                offers = await self._n(DecisionFacade).get_pre_approved(organization_id)
                return {o.product_code: o.max_amount for o in offers}

            pre_approved = await self._n.optional("pre_approved", load, {})
        found = sorted(
            await self._n(ProductsFacade).recommend(purpose, amount, term_months, organization_id),
            key=lambda r: r.rank,
        )
        best = next((r.product.code for r in found if r.eligible is not False), None)
        items = [
            views.Recommendation(
                product_code=r.product.code,
                product_name=r.product.name,
                short_description=r.product.short_description,
                rank=r.rank,
                fit="unavailable"
                if r.eligible is False
                else ("best" if r.product.code == best else "suitable"),
                eligible=r.eligible,
                eligibility=[views.EligibilityReason.model_validate(x) for x in r.reasons],
                rate_from=r.product.rate_base,
                amount_max=r.product.amount_max,
                term_max_months=r.product.term_max_months,
                payment_from=r.estimated_monthly_payment,
                pre_approved_max=pre_approved.get(r.product.code),
            )
            for r in found
        ]
        return views.Recommendations(items=items, degraded=self._n.degraded)

    # --- calculator with the pre-approval -----------------------------------

    async def personal_schedule(
        self,
        account_id: UUID,
        member_of: frozenset[UUID] | None,
        organization_id: UUID,
        code: str,
        amount: Decimal,
        term_months: int,
        repayment: Repayment | None,
    ) -> views.PersonalSchedule:
        """The rate is the bank's: the pre-approved one, the base one without it.
        A request above the pre-approved terms is not an error: the decision
        comes after the check, the bank may answer with a counteroffer."""
        await self._ensure_visible(account_id, member_of, organization_id)
        products = self._n(ProductsFacade)
        product = await products.get_product(code)
        check = await products.check_eligibility(code, organization_id)
        repayment = repayment or product.repayment_options[0]
        _ensure_within_product(product, amount, term_months, repayment)

        async def load() -> PreApprovedOfferDTO | None:
            offers = await self._n(DecisionFacade).get_pre_approved(organization_id)
            return next((o for o in offers if o.product_code == code), None)

        offer = await self._n.optional("pre_approved", load, None)
        rate = offer.rate_from if offer is not None else product.rate_base
        schedule = products.calculate_payment(amount, term_months, rate, repayment)
        reasons = [views.EligibilityReason.model_validate(r) for r in check.reasons]
        pre_approved: views.PreApprovedTerms | None = None
        within: bool | None = None
        suggestion: views.Suggestion | None = None
        if offer is not None:
            pre_approved = _terms(offer)
            above = _above_pre_approved(offer, amount, term_months)
            within = not above
            reasons += above
            if above:
                suggestion = _suggestion(products, product, offer, amount, term_months, repayment)
        return views.PersonalSchedule(
            schedule=views.PaymentSchedule.model_validate(schedule),
            pre_approved=pre_approved,
            within_pre_approved=within,
            eligible=check.eligible,
            reasons=reasons,
            suggestion=suggestion,
            degraded=self._n.degraded,
        )


def _ensure_within_product(
    product: ProductDTO, amount: Decimal, term_months: int, repayment: Repayment
) -> None:
    """The same 422 as `POST /products/{code}/calculate` gives."""
    if not product.amount_min <= amount <= product.amount_max:
        raise _out_of_range("amount", product.amount_min, product.amount_max)
    if not product.term_min_months <= term_months <= product.term_max_months:
        raise _out_of_range("term_months", product.term_min_months, product.term_max_months)
    if repayment not in product.repayment_options:
        raise ValidationError(
            "The product does not offer this schedule",
            details={
                "field": "repayment",
                "code": "not_offered",
                "options": list(product.repayment_options),
            },
        )


def _out_of_range(field: str, low: Decimal | int, high: Decimal | int) -> ValidationError:
    return ValidationError(
        "Value is out of the product frames",
        details={"field": field, "code": "out_of_range", "min": str(low), "max": str(high)},
    )


def _terms(offer: PreApprovedOfferDTO) -> views.PreApprovedTerms:
    return views.PreApprovedTerms(
        max_amount=offer.max_amount,
        rate_from=offer.rate_from,
        term_max_months=offer.term_max_months,
        valid_until=offer.valid_until,
        # Only the kind of the estimate leaves the bank, not what it is based on.
        basis="full" if offer.basis == "full" else "estimate",
    )


def _above_pre_approved(
    offer: PreApprovedOfferDTO, amount: Decimal, term_months: int
) -> list[views.EligibilityReason]:
    reasons = []
    if amount > offer.max_amount:
        reasons.append(
            views.EligibilityReason(
                code="amount_above_pre_approved",
                passed=False,
                message=f"Предварительно доступно до {_rub(offer.max_amount)}",
            )
        )
    if term_months > offer.term_max_months:
        reasons.append(
            views.EligibilityReason(
                code="term_above_pre_approved",
                passed=False,
                message=f"Предварительно доступен срок до {offer.term_max_months} мес.",
            )
        )
    return reasons


def _suggestion(
    products: ProductsFacade,
    product: ProductDTO,
    offer: PreApprovedOfferDTO,
    amount: Decimal,
    term_months: int,
    repayment: Repayment,
) -> views.Suggestion | None:
    """The request cut to the pre-approved amount and term; none when the cut
    falls below the product minimum."""
    amount = min(amount, offer.max_amount)
    term_months = min(term_months, offer.term_max_months)
    if amount < product.amount_min or term_months < product.term_min_months:
        return None
    schedule = products.calculate_payment(amount, term_months, offer.rate_from, repayment)
    return views.Suggestion(
        amount=amount, term_months=term_months, monthly_payment=schedule.monthly_payment
    )


def _rub(value: Decimal) -> str:
    """`Decimal("5000000")` -> `5 000 000 ₽`."""
    whole, _, kopecks = f"{value:,.2f}".replace(",", " ").partition(".")
    return f"{whole},{kopecks} ₽" if kopecks != "00" else f"{whole} ₽"


def _brief(summary: OrganizationSummaryDTO) -> views.OrganizationBrief:
    return views.OrganizationBrief(
        id=summary.id,
        name=summary.name,
        inn=summary.inn,
        legal_form=summary.legal_form,
        my_role=summary.my_role,
        my_permissions=sorted(summary.my_permissions),
    )


def _row(row: ApplicationOverviewDTO) -> views.ApplicationRow:
    return views.ApplicationRow(
        id=row.application_id,
        number=row.number,
        product_code=row.product_code,
        product_name=row.product_name,
        amount=row.amount,
        term_months=row.term_months,
        status=row.status,
        client_status=client_status(
            row.status, row.client_stage, offer_kind_of_row(row.amount, row.offer_amount)
        ),
        client_stage=row.client_stage,
        action_required=row.action_required,
        offer_amount=row.offer_amount,
        offer_rate=row.offer_rate,
        submitted_at=row.submitted_at,
        updated_at=row.updated_at,
    )


def _card(
    card: ApplicationCardDTO,
    product_name: str | None,
    timeline: list[TimelineEntryDTO],
    decision: ClientDecisionDTO | None,
    feed: list[FeedItemDTO],
    permissions: frozenset[str],
    degraded: list[str],
) -> views.ClientApplicationCard:
    terms = card.product_terms
    org = card.org_snapshot
    open_request = next((r for r in card.info_requests if r.status == "open"), None)
    client_decision: views.ClientDecision | None = None
    if decision is not None:
        client_decision = views.ClientDecision.model_validate(decision)
    elif card.decision_summary is not None:
        # The decision module is not reachable: the summary kept in the card is
        # the same client-safe text, without terms.
        client_decision = views.ClientDecision.model_validate(card.decision_summary)
    return views.ClientApplicationCard(
        id=card.id,
        number=card.number,
        organization=views.OrganizationRef(id=org.id, name=org.name, inn=org.inn) if org else None,
        product=views.ProductInfo(
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
        request=views.LoanRequest.model_validate(card.request) if card.request else None,
        product_fields=dict(card.product_fields),
        collateral=views.Collateral.model_validate(card.collateral) if card.collateral else None,
        documents=[views.Document.model_validate(d) for d in card.documents],
        info_request=views.InfoRequest.model_validate(open_request) if open_request else None,
        offer=views.Offer.model_validate(card.offer) if card.offer else None,
        decision=client_decision,
        timeline=[
            views.ClientTimelineEntry.model_validate(e) for e in timeline if e.audience == "client"
        ],
        feed=[views.FeedItem.model_validate(i) for i in feed],
        available_actions=available_actions(card.status, permissions),
        my_permissions=sorted(permissions),
        created_at=card.created_at,
        updated_at=card.updated_at,
        submitted_at=card.submitted_at,
        closed_at=card.closed_at,
        degraded=degraded,
    )
