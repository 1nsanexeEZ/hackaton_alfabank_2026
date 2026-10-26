from uuid import UUID, uuid4

import pytest

from src.core.exceptions.exceptions import NotFoundError, PermissionDeniedError
from src.modules.notifications.application.interfaces.access import OrganizationAccess
from src.modules.notifications.application.use_cases.organizations import (
    EnsureOrganizationVisibleUseCase,
    ViewerOrganizationsUseCase,
)

ACCOUNT = uuid4()
OWN = uuid4()
STRANGER = uuid4()


class RecordingAccess(OrganizationAccess):
    def __init__(self) -> None:
        self.checked: list[UUID] = []
        self.listed: list[UUID] = []

    async def ensure_can_view(self, account_id: UUID, organization_id: UUID) -> None:
        self.checked.append(organization_id)
        if organization_id != OWN:
            raise PermissionDeniedError("not a member")

    async def member_organizations(self, account_id: UUID) -> frozenset[UUID]:
        self.listed.append(account_id)
        return frozenset({OWN})


async def test_own_company_passes() -> None:
    access = RecordingAccess()
    await EnsureOrganizationVisibleUseCase(access).execute(ACCOUNT, False, OWN)
    assert access.checked == [OWN]


async def test_strangers_company_is_not_found() -> None:
    with pytest.raises(NotFoundError):
        await EnsureOrganizationVisibleUseCase(RecordingAccess()).execute(ACCOUNT, False, STRANGER)


@pytest.mark.parametrize("bank_staff,organization_id", [(True, STRANGER), (False, None)])
async def test_no_check_for_bank_staff_or_without_filter(
    bank_staff: bool, organization_id: UUID | None
) -> None:
    access = RecordingAccess()
    await EnsureOrganizationVisibleUseCase(access).execute(ACCOUNT, bank_staff, organization_id)
    assert access.checked == []


async def test_client_reads_only_the_companies_they_are_a_member_of() -> None:
    access = RecordingAccess()
    assert await ViewerOrganizationsUseCase(access).execute(ACCOUNT, False) == {OWN}
    assert access.listed == [ACCOUNT]


async def test_bank_staff_read_any_company() -> None:
    access = RecordingAccess()
    assert await ViewerOrganizationsUseCase(access).execute(ACCOUNT, True) is None
    assert access.listed == []
