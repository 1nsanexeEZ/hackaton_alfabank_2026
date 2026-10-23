import re
from datetime import datetime
from uuid import UUID, uuid4

from src.modules.identity.facade import (
    AccountRefDTO,
    CompanyConsentType,
    ConsentDTO,
    PersonalConsentType,
)


def _normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits[0] == "8":
        digits = "7" + digits[1:]
    return "+" + digits


class FakeIdentityFacade:
    def __init__(self) -> None:
        self.accounts: dict[UUID, AccountRefDTO] = {}
        self.passwords: dict[UUID, str] = {}
        # Consents in force: (account, type) -> consent.
        self.consents: dict[tuple[UUID, str], ConsentDTO] = {}
        # Company consents in force: (organization, type) -> consent.
        self.organization_consents: dict[tuple[UUID, str], ConsentDTO] = {}

    def add_account(
        self,
        email: str | None = None,
        phone: str | None = None,
        role_name: str = "client",
        password: str = "Password-1",
        last_name: str = "Тестов",
        first_name: str = "Тест",
        account_id: UUID | None = None,
    ) -> AccountRefDTO:
        account = AccountRefDTO(
            id=account_id or uuid4(),
            email=email.lower() if email else None,
            phone=_normalize_phone(phone) if phone else None,
            role_name=role_name,
            last_name=last_name,
            first_name=first_name,
        )
        self.accounts[account.id] = account
        self.passwords[account.id] = password
        return account

    def give_consent(
        self,
        account_id: UUID,
        type: PersonalConsentType,
        given_at: datetime,
        valid_until: datetime | None = None,
    ) -> ConsentDTO:
        consent = ConsentDTO(account_id, type, given_at, valid_until, "test")
        self.consents[(account_id, type)] = consent
        return consent

    def give_organization_consent(
        self,
        organization_id: UUID,
        account_id: UUID,
        given_at: datetime,
        type: CompanyConsentType = "credit_bureau_company",
        valid_until: datetime | None = None,
    ) -> ConsentDTO:
        consent = ConsentDTO(account_id, type, given_at, valid_until, "test", organization_id)
        self.organization_consents[(organization_id, type)] = consent
        return consent

    async def get_account(self, account_id: UUID) -> AccountRefDTO | None:
        return self.accounts.get(account_id)

    async def find_by_login(self, login: str) -> AccountRefDTO | None:
        if "@" in login:
            return next((a for a in self.accounts.values() if a.email == login.lower()), None)
        phone = _normalize_phone(login)
        return next((a for a in self.accounts.values() if a.phone == phone), None)

    async def verify_password(self, account_id: UUID, password: str) -> bool:
        return self.passwords.get(account_id) == password

    async def get_active_consent(
        self, account_id: UUID, type: PersonalConsentType
    ) -> ConsentDTO | None:
        return self.consents.get((account_id, type))

    async def get_active_organization_consent(
        self, organization_id: UUID, type: CompanyConsentType
    ) -> ConsentDTO | None:
        return self.organization_consents.get((organization_id, type))
