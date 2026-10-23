from dataclasses import dataclass
from typing import Self
from uuid import UUID

from src.modules.bff.domain.enums import Segment
from src.modules.clients.facade import OrganizationSummaryDTO


@dataclass(frozen=True, slots=True)
class OrganizationBriefDTO:
    id: UUID
    name: str
    inn: str
    legal_form: str
    my_role: str
    my_permissions: tuple[str, ...]

    @classmethod
    def of(cls, summary: OrganizationSummaryDTO) -> Self:
        return cls(
            id=summary.id,
            name=summary.name,
            inn=summary.inn,
            legal_form=summary.legal_form,
            my_role=summary.my_role,
            my_permissions=tuple(sorted(summary.my_permissions)),
        )


@dataclass(frozen=True, slots=True)
class CurrentOrganizationDTO(OrganizationBriefDTO):
    verification_status: str
    registry_status: str
    segment: Segment = "established"
