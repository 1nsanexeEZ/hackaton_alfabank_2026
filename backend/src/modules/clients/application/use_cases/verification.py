"""Check of a company against ЕГРЮЛ/ЕГРИП (step 5 of the client journey):
the card follows the registry, the head is left for a person.

Two entry points: `VerifyOrganizationUseCase` — on request, in its own
transaction, the registry asked past the cache; `ApplyRegistryExtractUseCase`
— with the extract enrichment already fetched for an application, inside the
transaction of the message handler (the processor commits).
"""

from uuid import UUID, uuid4

from src.core.access.access_context import AccessContext
from src.core.domain.clock import Clock
from src.core.exceptions.exceptions import ValidationError
from src.core.uow import UnitOfWork
from src.modules.clients.application.dto.organizations import VerificationResultDTO
from src.modules.clients.application.interfaces.outbox import EventOutbox
from src.modules.clients.application.interfaces.registry import RegistryLookup
from src.modules.clients.application.interfaces.repositories import OrganizationRepository
from src.modules.clients.application.mappers.events import stage
from src.modules.clients.application.use_cases.common import get_organization, person_of
from src.modules.clients.domain.organization import Organization
from src.modules.clients.domain.value_objects import PersonName, RegistryChanges, RegistryExtract
from src.modules.identity.facade import IdentityFacade


class _RegistryCheck:
    """The card brought to the extract; the change and its events are staged
    in the current transaction."""

    def __init__(
        self,
        organizations: OrganizationRepository,
        outbox: EventOutbox,
        clock: Clock,
        identity: IdentityFacade,
    ) -> None:
        self._organizations = organizations
        self._outbox = outbox
        self._clock = clock
        self._identity = identity

    async def apply(
        self,
        org: Organization,
        extract: RegistryExtract,
        *,
        correlation_id: UUID,
        causation_id: UUID | None = None,
    ) -> RegistryChanges:
        declared = await self._declared_heads(org)
        changes = org.apply_registry(extract, self._clock.now(), declared=declared)
        await self._organizations.save(org)
        events = org.pull_events()
        await stage(self._outbox, events, correlation_id=correlation_id, causation_id=causation_id)
        return changes

    async def _declared_heads(self, org: Organization) -> dict[UUID, PersonName]:
        """Names of the members acting as the head; an account without a
        usable name is not compared."""
        names: dict[UUID, PersonName] = {}
        for account_id in org.declared_heads():
            account = await self._identity.get_account(account_id)
            person = person_of(account) if account is not None else None
            if person is not None:
                names[account_id] = person
        return names


class VerifyOrganizationUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        organizations: OrganizationRepository,
        outbox: EventOutbox,
        clock: Clock,
        registry: RegistryLookup,
        identity: IdentityFacade,
    ) -> None:
        self._uow = uow
        self._organizations = organizations
        self._clock = clock
        self._registry = registry
        self._check = _RegistryCheck(organizations, outbox, clock, identity)

    async def execute(self, access: AccessContext, organization_id: UUID) -> VerificationResultDTO:
        """Unknown INN — 422 `registry_not_found`; the registry did not answer
        — InfrastructureError (503) and the check stays as it was."""
        async with self._uow:
            org = await get_organization(self._organizations, organization_id, access)
            extract = await self._registry.lookup(org.requisites.inn.value)
            if extract is None:
                raise ValidationError(
                    "The registry does not know this INN",
                    details={"field": "inn", "code": "registry_not_found"},
                )
            changes = await self._check.apply(org, extract, correlation_id=uuid4())
            await self._uow.commit()
        return VerificationResultDTO.of(org, changes, access.user_id, self._clock.now())


class ApplyRegistryExtractUseCase:
    """Auto check: every application brings a fresh ЕГРЮЛ extract, and the
    company follows it with no extra request to the registry. No commit here:
    the message processor commits the handler's transaction with the inbox."""

    def __init__(
        self,
        organizations: OrganizationRepository,
        outbox: EventOutbox,
        clock: Clock,
        registry: RegistryLookup,
        identity: IdentityFacade,
    ) -> None:
        self._organizations = organizations
        self._registry = registry
        self._check = _RegistryCheck(organizations, outbox, clock, identity)

    async def execute(
        self, application_id: UUID, *, correlation_id: UUID, causation_id: UUID
    ) -> RegistryChanges | None:
        """None — skipped: no readable extract for the application (the source
        failed), an unknown company or an extract for another INN."""
        found = await self._registry.of_application(application_id)
        if found is None:
            return None
        organization_id, extract = found
        org = await self._organizations.get(organization_id)
        if org is None or org.requisites.inn != extract.inn:
            return None
        return await self._check.apply(
            org, extract, correlation_id=correlation_id, causation_id=causation_id
        )
