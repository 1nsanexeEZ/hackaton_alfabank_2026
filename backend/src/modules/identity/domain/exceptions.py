"""Broken identity rules. No HTTP here: infrastructure/exception_handler.py maps
each error to a response."""


class IdentityError(Exception):
    default_message = "Identity error"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


class InvalidCredentialsError(IdentityError):
    default_message = "Invalid login or password"


class InvalidTokenError(IdentityError):
    default_message = "Invalid token"


class TokenExpiredError(IdentityError):
    default_message = "Token expired"


class AccountNotFoundError(IdentityError):
    """No such account among those the caller may see."""

    default_message = "Account not found"


class CurrentAccountNotFoundError(IdentityError):
    """The token's own account is gone (deleted after the token was issued)."""

    default_message = "Account not found"


class DemoAccountNotFoundError(IdentityError):
    default_message = "Demo account not found"


class RoleNotFoundError(IdentityError):
    """No such role among those the caller may see."""

    default_message = "Role not found"


class UnknownRoleError(IdentityError):
    """An account is given a role that doesn't exist."""

    default_message = "Role not found"


class RoleAlreadyExistsError(IdentityError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Role {name!r} already exists")


class RoleInUseError(IdentityError):
    default_message = "Role is assigned to accounts"


class OrphanedPoliciesError(IdentityError):
    def __init__(self, permissions: list[str]) -> None:
        super().__init__(f"Policies set for permissions the role doesn't have: {permissions}")


class LoginTakenError(IdentityError):
    default_message = "Email or phone is already taken"


class LoginRequiredError(IdentityError):
    default_message = "Either email or phone is required"


class SelfDeletionError(IdentityError):
    default_message = "You can't delete your own account"


class EmptyNameError(IdentityError):
    def __init__(self, field: str) -> None:
        super().__init__(f"{field} can't be empty")
