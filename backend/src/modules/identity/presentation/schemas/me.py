from typing import Self

from src.core.schemas.jwt_dto import OpenSubTokenDTO
from src.modules.identity.application.dto.accounts import AccountDTO
from src.modules.identity.presentation.schemas.accounts import AccountRead


class MeRead(AccountRead):
    permissions: list[str]
    policies: dict[str, list[str]]

    @classmethod
    def build(cls, account: AccountDTO, token: OpenSubTokenDTO) -> Self:
        # Rights are taken from the token: that's what every module will enforce
        # until it expires, even if the role was edited in the meantime.
        return cls(
            **AccountRead.model_validate(account).model_dump(),
            permissions=token.permissions,
            policies=token.policies,
        )
