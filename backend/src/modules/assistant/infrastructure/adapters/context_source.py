"""The assistant's reads over the neighbours' facades.

Only client-safe fields are carried over to the views: the decision comes from
`DecisionFacade.get_client_view` (no score, reason codes or rule trace), and of
the application card the company's name, INN and the rest of its snapshot are
dropped here, before the domain. Access is the same as on the client's
application card: a company the viewer is not a member of is 404.
"""

from decimal import Decimal
from uuid import UUID

from src.core.exceptions.exceptions import NotFoundError, ValidationError
from src.modules.applications.facade import (
    ApplicationCardDTO,
    ApplicationsFacade,
    ApplicationSummaryDTO,
)
from src.modules.assistant.application.interfaces.context import ContextSource
from src.modules.assistant.domain.exceptions import ApplicationNotFoundError
from src.modules.assistant.domain.views import (
    ApplicationView,
    ClientDecisionView,
    DecisionTermsView,
    InfoRequestView,
    LoanRequestView,
    PaymentView,
    ProductView,
    RequestedInfoView,
    RequiredDocumentView,
    Viewer,
)
from src.modules.clients.facade import ClientsFacade, OrgPermission
from src.modules.decision.facade import ClientDecisionDTO, DecisionFacade
from src.modules.products.facade import ProductDTO, ProductsFacade, Repayment


class FacadeContextSource(ContextSource):
    """One per request: the cards it has read are kept for the rest of the answer."""

    def __init__(
        self,
        applications: ApplicationsFacade,
        decision: DecisionFacade,
        products: ProductsFacade,
        clients: ClientsFacade,
    ) -> None:
        self._applications = applications
        self._decision = decision
        self._products = products
        self._clients = clients
        self._seen: dict[UUID, ApplicationView] = {}

    async def get_application(self, viewer: Viewer, application_id: UUID) -> ApplicationView:
        if application_id in self._seen:
            return self._seen[application_id]
        try:
            card = await self._applications.get_card(application_id)
        except NotFoundError:
            raise ApplicationNotFoundError() from None
        if not viewer.may_see(card.organization_id):
            raise ApplicationNotFoundError()
        can_sign = False
        if viewer.organization_ids is not None:
            rights = await self._clients.get_member_permissions(
                viewer.account_id, card.organization_id
            )
            if OrgPermission.VIEW not in rights:
                raise ApplicationNotFoundError()
            can_sign = OrgPermission.SIGN in rights
        view = _application(card, can_sign)
        self._seen[application_id] = view
        return view

    async def list_applications(self, viewer: Viewer) -> list[ApplicationView]:
        if viewer.organization_ids is None:
            # Bank staff ask about an application by its id: no list of every application.
            return []
        rows = [
            _row(summary)
            for organization_id in viewer.organization_ids
            for summary in await self._applications.list_for_organization(organization_id)
        ]
        return sorted(rows, key=lambda a: a.number)

    async def get_client_decision(
        self, viewer: Viewer, application_id: UUID
    ) -> ClientDecisionView | None:
        await self.get_application(viewer, application_id)
        decision = await self._decision.get_client_view(application_id)
        return _decision(decision) if decision else None

    async def list_products(self) -> list[ProductView]:
        return [_product(p) for p in await self._products.list_active()]

    def calculate_payment(
        self, amount: Decimal, term_months: int, rate: Decimal, repayment: str
    ) -> PaymentView:
        try:
            schedule = self._products.calculate_payment(
                amount, term_months, rate, _repayment(repayment)
            )
        except ValidationError as error:
            raise ValueError(error.message) from None
        return PaymentView(
            amount=schedule.amount,
            term_months=schedule.term_months,
            rate=schedule.rate,
            repayment=schedule.repayment,
            monthly_payment=schedule.monthly_payment,
            total_interest=schedule.total_interest,
            total_paid=schedule.total_paid,
        )


def _repayment(value: str) -> Repayment:
    match value:
        case "annuity" | "differentiated" | "interest_only" | "by_contract_schedule":
            return value
    raise ValueError(f"unknown repayment {value!r}")


def _application(card: ApplicationCardDTO, can_sign: bool) -> ApplicationView:
    request = card.request
    return ApplicationView(
        id=card.id,
        number=card.number,
        organization_id=card.organization_id,
        product_code=card.product_code,
        status=card.status,
        client_stage=card.client_stage,
        request=LoanRequestView(
            amount=request.amount,
            term_months=request.term_months,
            purpose=request.purpose,
            purpose_comment=request.purpose_comment,
        )
        if request
        else None,
        info_requests=tuple(
            InfoRequestView(
                requested_fields=r.requested_fields,
                requested_documents=r.requested_documents,
                comment=r.comment,
                due_at=r.due_at,
                status=r.status,
            )
            for r in card.info_requests
        ),
        updated_at=card.updated_at,
        viewer_can_sign=can_sign,
    )


def _row(summary: ApplicationSummaryDTO) -> ApplicationView:
    """A list row has no request or info requests: the whole card is read when needed."""
    return ApplicationView(
        id=summary.id,
        number=summary.number,
        organization_id=summary.organization_id,
        product_code=summary.product_code,
        status=summary.status,
        client_stage=summary.client_stage,
        request=None,
        info_requests=(),
        updated_at=summary.updated_at,
    )


def _decision(decision: ClientDecisionDTO) -> ClientDecisionView:
    terms = decision.terms
    info = decision.requested_info
    return ClientDecisionView(
        outcome=decision.outcome,
        terms=DecisionTermsView(
            amount=terms.amount,
            term_months=terms.term_months,
            rate=terms.rate,
            monthly_payment=terms.monthly_payment,
            schedule_type=terms.schedule_type,
            conditions=terms.conditions,
            expires_at=terms.expires_at,
        )
        if terms
        else None,
        alternative_product_code=decision.alternative_product_code,
        client_explanation=decision.client_explanation,
        improvement_hints=decision.improvement_hints,
        requested_info=RequestedInfoView(
            fields=info.fields, documents=info.documents, comment=info.comment
        )
        if info
        else None,
    )


def _product(product: ProductDTO) -> ProductView:
    program = product.support_program
    return ProductView(
        code=product.code,
        name=product.name,
        short_description=product.short_description,
        description_plain=product.description_plain,
        purposes=product.purposes,
        facility=product.facility,
        repayment_options=product.repayment_options,
        amount_min=product.amount_min,
        amount_max=product.amount_max,
        term_min_months=product.term_min_months,
        term_max_months=product.term_max_months,
        rate_base=product.rate_base,
        rate_max=product.rate_max,
        collateral_kind=product.collateral_kind,
        collateral_types=product.collateral_types,
        min_business_age_months=product.min_business_age_months,
        min_annual_revenue=product.min_annual_revenue,
        required_documents=tuple(
            RequiredDocumentView(
                type=d.type,
                title=d.title,
                required_from_amount=d.required_from_amount,
                legal_forms=d.legal_forms,
            )
            for d in product.required_documents
        ),
        support_program_name=program.name if program else None,
        support_rate_cap=program.rate_cap if program else None,
    )
