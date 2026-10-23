from typing import Protocol


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password_hash: str, password: str) -> bool:
        """False for a wrong password and for a hash it can't read."""
        ...

    def verify_dummy(self, password: str) -> None:
        """Takes as long as verify(): run when the login doesn't exist, so a wrong
        login can't be told from a wrong password by timing."""
        ...

    def needs_rehash(self, password_hash: str) -> bool: ...
