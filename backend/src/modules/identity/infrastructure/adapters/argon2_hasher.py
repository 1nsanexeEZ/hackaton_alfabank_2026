from argon2 import PasswordHasher as Argon2Hasher
from argon2.exceptions import InvalidHashError, VerificationError

from src.modules.identity.application.interfaces.password_hasher import PasswordHasher


class Argon2PasswordHasher(PasswordHasher):
    """argon2id with library defaults."""

    def __init__(self) -> None:
        self._hasher = Argon2Hasher()
        # Verified against when the login doesn't exist, so a wrong login
        # takes as long as a wrong password.
        self._dummy_hash = self._hasher.hash("dummy-password")

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    def verify_dummy(self, password: str) -> None:
        self.verify(self._dummy_hash, password)

    def needs_rehash(self, password_hash: str) -> bool:
        return self._hasher.check_needs_rehash(password_hash)
