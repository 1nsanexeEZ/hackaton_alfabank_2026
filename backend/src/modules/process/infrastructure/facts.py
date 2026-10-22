from uuid import UUID

from src.modules.applications.facade import ApplicationsFacade
from src.modules.process.domain.steps import CollateralFact, CompletenessFact, EnrichmentRequestFact


class ApplicationFacts:
    """What the steps need to know about the application, read through the
    applications facade (the data frozen at submission)."""

    def __init__(self, applications: ApplicationsFacade) -> None:
        self._applications = applications

    async def completeness(self, application_id: UUID) -> CompletenessFact:
        result = await self._applications.get_completeness(application_id)
        return CompletenessFact(result.complete, result.missing_fields, result.missing_documents)

    async def enrichment_request(self, application_id: UUID) -> EnrichmentRequestFact:
        data = await self._applications.get_scoring_input(application_id)
        return EnrichmentRequestFact(
            inn=data.organization.inn,
            bki_consent_at=data.credit_bureau_consent_at,
            statement_document_ids=data.statement_document_ids,
        )

    async def collateral(self, application_id: UUID) -> CollateralFact | None:
        card = await self._applications.get_card(application_id)
        if card.collateral is None:
            return None
        return CollateralFact(card.collateral.type, card.collateral.declared_value)
