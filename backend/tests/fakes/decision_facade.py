from collections.abc import Sequence
from uuid import UUID

from src.modules.decision.facade import (
    ClientDecisionDTO,
    DecisionDTO,
    FounderPrescreenDTO,
    PreApprovedOfferDTO,
    ProjectAssessmentDTO,
)


class FakeDecisionFacade:
    def __init__(self) -> None:
        self.decisions: dict[UUID, DecisionDTO] = {}
        self.pre_approved: dict[UUID, list[PreApprovedOfferDTO]] = {}
        self.prescreens: dict[UUID, FounderPrescreenDTO] = {}
        self.projects: dict[UUID, ProjectAssessmentDTO] = {}

    def set_project(self, organization_id: UUID, assessment: ProjectAssessmentDTO) -> None:
        self.projects[organization_id] = assessment

    async def get_project_assessment(self, organization_id: UUID) -> ProjectAssessmentDTO | None:
        return self.projects.get(organization_id)

    def set_prescreen(self, organization_id: UUID, prescreen: FounderPrescreenDTO) -> None:
        self.prescreens[organization_id] = prescreen

    async def get_founder_prescreen(self, organization_id: UUID) -> FounderPrescreenDTO | None:
        return self.prescreens.get(organization_id)

    def add_decision(self, decision: DecisionDTO) -> DecisionDTO:
        self.decisions[decision.application_id] = decision
        return decision

    def set_pre_approved(self, organization_id: UUID, offers: list[PreApprovedOfferDTO]) -> None:
        self.pre_approved[organization_id] = offers

    async def get_decision(self, application_id: UUID) -> DecisionDTO | None:
        return self.decisions.get(application_id)

    async def get_decisions(self, application_ids: Sequence[UUID]) -> dict[UUID, DecisionDTO]:
        return {i: self.decisions[i] for i in application_ids if i in self.decisions}

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
