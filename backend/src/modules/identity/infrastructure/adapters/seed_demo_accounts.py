from seed.demo_data import ACCOUNTS, ACCOUNTS_BY_EMAIL
from src.modules.identity.application.dto.auth import DemoAccountEntryDTO
from src.modules.identity.application.interfaces.demo_accounts import DemoAccountCatalog


class SeedDemoAccountCatalog(DemoAccountCatalog):
    """The demo accounts declared in `seed.demo_data`."""

    def list(self) -> list[DemoAccountEntryDTO]:
        return [
            DemoAccountEntryDTO(email=account.email, caption=account.caption)
            for account in ACCOUNTS
        ]

    def contains(self, email: str) -> bool:
        return email in ACCOUNTS_BY_EMAIL
