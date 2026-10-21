import re
from uuid import UUID, uuid4

from src.identity.facade import AccountRefDTO


def _normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits[0] == "8":
        digits = "7" + digits[1:]
    return "+" + digits


class FakeIdentityFacade:
    def __init__(self) -> None:
        self.accounts: dict[UUID, AccountRefDTO] = {}
        self.passwords: dict[UUID, str] = {}

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

    async def get_account(self, account_id: UUID) -> AccountRefDTO | None:
        return self.accounts.get(account_id)

    async def find_by_login(self, login: str) -> AccountRefDTO | None:
        if "@" in login:
            return next((a for a in self.accounts.values() if a.email == login.lower()), None)
        phone = _normalize_phone(login)
        return next((a for a in self.accounts.values() if a.phone == phone), None)

    async def verify_password(self, account_id: UUID, password: str) -> bool:
        return self.passwords.get(account_id) == password
