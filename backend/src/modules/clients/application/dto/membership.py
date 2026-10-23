"""Companies of an account with its role and rights. Re-exported by facade.py."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from src.modules.clients.application.dto.snapshot import LegalForm

MemberRole = Literal["owner", "director", "accountant", "employee"]


@dataclass(frozen=True, slots=True)
class OrganizationSummaryDTO:
    id: UUID
    name: str
    inn: str
    legal_form: LegalForm
    my_role: MemberRole
    my_permissions: frozenset[str]
