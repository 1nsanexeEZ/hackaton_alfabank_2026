from datetime import datetime
from uuid import UUID

from src.modules.applications.facade import ApplicationsFacade, ScoringInputDTO
from src.modules.clients.facade import ClientsFacade
from src.modules.identity.facade import IdentityFacade
from src.modules.process.domain.steps import (
    CollateralFact,
    CompletenessFact,
    DeclaredOwnerFact,
    EnrichmentRequestFact,
    PersonFact,
    ProcessFacts,
    ThirdPartyFact,
)


class ApplicationFacts(ProcessFacts):
    """What the steps need to know about the application, read through the
    applications facade (the data frozen at submission). The head of the company and
    their personal consent are read live: the consent may come after submission."""

    def __init__(
        self,
        applications: ApplicationsFacade,
        clients: ClientsFacade,
        identity: IdentityFacade,
    ) -> None:
        self._applications = applications
        self._clients = clients
        self._identity = identity

    async def completeness(self, application_id: UUID) -> CompletenessFact:
        result = await self._applications.get_completeness(application_id)
        return CompletenessFact(result.complete, result.missing_fields, result.missing_documents)

    async def enrichment_request(self, application_id: UUID) -> EnrichmentRequestFact:
        data = await self._applications.get_scoring_input(application_id)
        head, head_consent_at = await self._head(data.organization_id)
        return EnrichmentRequestFact(
            inn=data.organization.inn,
            bki_consent_at=data.credit_bureau_consent_at,
            statement_document_ids=data.statement_document_ids,
            head=head,
            head_bki_consent_at=head_consent_at,
            representative=await self._representative(data.applicant_account_id, head),
            third_parties=_third_parties(data),
            declared_owners=_declared_owners(data),
        )

    async def collateral(self, application_id: UUID) -> CollateralFact | None:
        card = await self._applications.get_card(application_id)
        if card.collateral is None:
            return None
        return CollateralFact(card.collateral.type, card.collateral.declared_value)

    async def _representative(
        self, account_id: UUID | None, head: PersonFact | None
    ) -> PersonFact | None:
        """Who submitted the application acts for the client; the head is screened anyway."""
        if account_id is None or (head is not None and head.account_id == account_id):
            return None
        account = await self._identity.get_account(account_id)
        if account is None:
            return None
        return PersonFact(account.id, account.last_name, account.first_name, account.middle_name)

    async def _head(self, organization_id: UUID) -> tuple[PersonFact | None, datetime | None]:
        """Registry head → their account → their consent in force to request the bureau."""
        account_id = await self._clients.get_registry_head(organization_id)
        if account_id is None:
            return None, None
        account = await self._identity.get_account(account_id)
        if account is None:
            return None, None
        consent = await self._identity.get_active_consent(account_id, "credit_bureau_personal")
        person = PersonFact(account.id, account.last_name, account.first_name, account.middle_name)
        return person, consent.given_at if consent is not None else None


def _third_parties(data: ScoringInputDTO) -> tuple[ThirdPartyFact, ...]:
    """The beneficiary the client acts for and the owner of the collateral, if declared."""
    parties: list[ThirdPartyFact] = []
    declaration = data.beneficiary
    if declaration is not None and declaration.beneficiary is not None:
        b = declaration.beneficiary
        parties.append(ThirdPartyFact("beneficiary", b.kind, b.name, b.inn, b.country))
    owner = data.collateral.owner_party if data.collateral is not None else None
    if owner is not None:
        parties.append(ThirdPartyFact("pledgor", owner.kind, owner.name, owner.inn, owner.country))
    return tuple(parties)


def _declared_owners(data: ScoringInputDTO) -> tuple[DeclaredOwnerFact, ...] | None:
    """The beneficial owners in the client's words; None — not answered."""
    if data.beneficial_owners is None:
        return None
    return tuple(
        DeclaredOwnerFact(o.name, o.basis, o.country) for o in data.beneficial_owners.owners
    )
