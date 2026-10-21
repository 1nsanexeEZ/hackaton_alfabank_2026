from uuid import UUID

from src.decision.facade import ClientDecisionDTO, DecisionDTO, PreApprovedOfferDTO


class FakeDecisionFacade:
    def __init__(self) -> None:
        self.decisions: dict[UUID, DecisionDTO] = {}
        self.pre_approved: dict[UUID, list[PreApprovedOfferDTO]] = {}

    def add_decision(self, decision: DecisionDTO) -> DecisionDTO:
        self.decisions[decision.application_id] = decision
        return decision

    def set_pre_approved(self, organization_id: UUID, offers: list[PreApprovedOfferDTO]) -> None:
        self.pre_approved[organization_id] = offers

    async def get_decision(self, application_id: UUID) -> DecisionDTO | None:
        return self.decisions.get(application_id)

    async def get_client_view(self, application_id: UUID) -> ClientDecisionDTO | None:
        decision = self.decisions.get(application_id)
        if decision is None:
            return None
        return ClientDecisionDTO(
            outcome=decision.outcome,
            terms=decision.terms,
            alternative_product_code=decision.alternative_product_code,
            client_explanation=decision.client_explanation,
            improvement_hints=decision.improvement_hints,
            requested_info=decision.requested_info,
        )

    async def get_pre_approved(self, organization_id: UUID) -> list[PreApprovedOfferDTO]:
        return list(self.pre_approved.get(organization_id, []))
