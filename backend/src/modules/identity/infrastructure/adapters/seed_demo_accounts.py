from seed.demo_data import ACCOUNTS, ACCOUNTS_BY_EMAIL
from src.modules.identity.application.dto.auth import DemoAccountEntryDTO
from src.modules.identity.application.interfaces.demo_accounts import DemoAccountCatalog
from src.modules.identity.domain.login_policy import normalize_email

ADMIN_CAPTION = "Администратор"


class SeedDemoAccountCatalog(DemoAccountCatalog):
    """The demo accounts declared in `seed.demo_data`, then the bootstrap admin
    (BOOTSTRAP_ADMIN_EMAIL), when there is one."""

    def __init__(self, admin_email: str | None = None) -> None:
        self._admin_email = normalize_email(admin_email) if admin_email else None

    def list(self) -> list[DemoAccountEntryDTO]:
        entries = [
            DemoAccountEntryDTO(email=account.email, caption=account.caption)
            for account in ACCOUNTS
        ]
        if self._admin_email is not None:
            entries.append(DemoAccountEntryDTO(email=self._admin_email, caption=ADMIN_CAPTION))
        return entries

    def contains(self, email: str) -> bool:
        return email in ACCOUNTS_BY_EMAIL or email == self._admin_email
