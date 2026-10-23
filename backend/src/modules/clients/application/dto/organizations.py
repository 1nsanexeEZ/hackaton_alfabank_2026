"""The company card for the companies API: what the caller sees with their own
role and rights at `now`."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Self
from uuid import UUID

from src.modules.clients.application.dto.snapshot import DiscrepancyDTO
from src.modules.clients.domain.organization import Organization
from src.modules.clients.domain.rights import ordered
from src.modules.clients.domain.value_objects import Discrepancy, RegistryChanges


def discrepancy_dto(discrepancy: Discrepancy) -> DiscrepancyDTO:
    return DiscrepancyDTO(
        field=discrepancy.field, declared=discrepancy.declared, registry=discrepancy.registry
    )


@dataclass(frozen=True, slots=True)
class AddressDTO:
    full: str
    region_code: str


@dataclass(frozen=True, slots=True)
class VerificationDTO:
    status: str
    checked_at: datetime | None
    discrepancies: tuple[DiscrepancyDTO, ...]


@dataclass(frozen=True, slots=True)
class OrganizationCardDTO:
    id: UUID
    name: str
    inn: str
    legal_form: str
    registry_status: str
    # None — the caller is not a member (bank staff).
    my_role: str | None
    my_permissions: tuple[str, ...]
    ogrn: str
    kpp: str | None
    registered_at: date
    business_age_months: int
    address: AddressDTO
    okved_main: str
    okved_extra: tuple[str, ...]
    tax_regime: str
    employees_count: int
    # Head by the registry (ЕГРЮЛ/ЕГРИП).
    head_name: str | None
    verification: VerificationDTO
    version: int

    @classmethod
    def of(cls, org: Organization, account_id: UUID, now: datetime) -> Self:
        requisites = org.requisites
        verification = org.verification
        member = org.is_member(account_id)
        return cls(
            id=org.id,
            name=org.name,
            inn=requisites.inn.value,
            legal_form=org.legal_form.value,
            registry_status=org.registry_status.value,
            my_role=org.member(account_id).role.value if member else None,
            my_permissions=tuple(p.value for p in ordered(org.permissions_of(account_id, now))),
            ogrn=requisites.ogrn.value,
            kpp=requisites.kpp.value if requisites.kpp else None,
            registered_at=org.registered_at,
            business_age_months=org.business_age_months(now),
            address=AddressDTO(full=org.address.full, region_code=org.address.region_code),
            okved_main=org.okved_main.value,
            okved_extra=tuple(code.value for code in org.okved_extra),
            tax_regime=org.tax_regime.value,
            employees_count=org.employees_count,
            head_name=org.registry_head.full if org.registry_head else None,
            verification=VerificationDTO(
                status=verification.status.value,
                checked_at=verification.checked_at,
                discrepancies=tuple(discrepancy_dto(d) for d in verification.discrepancies),
            ),
            version=org.version,
        )


@dataclass(frozen=True, slots=True)
class FieldChangeDTO:
    # `name`, `address.full`, `address.region_code`, `kpp`, `okved_main`,
    # `okved_extra` (codes joined with ", "), `registry_status`.
    field: str
    before: str | None
    after: str | None


@dataclass(frozen=True, slots=True)
class VerificationResultDTO:
    """Outcome of the check against ЕГРЮЛ/ЕГРИП: what followed the registry
    silently and what is left for a person."""

    organization: OrganizationCardDTO
    updated_fields: tuple[FieldChangeDTO, ...]
    discrepancies: tuple[DiscrepancyDTO, ...]

    @classmethod
    def of(
        cls, org: Organization, changes: RegistryChanges, account_id: UUID, now: datetime
    ) -> Self:
        return cls(
            organization=OrganizationCardDTO.of(org, account_id, now),
            updated_fields=tuple(
                FieldChangeDTO(field=c.field, before=c.before, after=c.after)
                for c in changes.updated
            ),
            discrepancies=tuple(discrepancy_dto(d) for d in changes.discrepancies),
        )
