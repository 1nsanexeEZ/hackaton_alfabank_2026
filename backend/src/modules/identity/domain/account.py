from dataclasses import dataclass
from datetime import datetime
from typing import Self
from uuid import UUID, uuid4

from src.modules.identity.domain.entities import Role
from src.modules.identity.domain.exceptions import LoginRequiredError
from src.modules.identity.domain.profile import Profile


@dataclass(slots=True)
class Account:
    """Someone who logs in by email, phone or either of the two. A deleted account
    is kept (soft delete) but can't log in."""

    id: UUID
    email: str | None
    phone: str | None
    password_hash: str
    role: Role
    profile: Profile
    # Filled by the repository once the account is stored.
    created_at: datetime | None = None
    deleted_at: datetime | None = None

    @classmethod
    def register(
        cls,
        *,
        email: str | None,
        phone: str | None,
        password_hash: str,
        role: Role,
        profile: Profile,
    ) -> Self:
        if email is None and phone is None:
            raise LoginRequiredError()
        return cls(
            id=uuid4(),
            email=email,
            phone=phone,
            password_hash=password_hash,
            role=role,
            profile=profile,
        )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def change_login(self, email: str | None, phone: str | None) -> None:
        if email is None and phone is None:
            raise LoginRequiredError()
        self.email, self.phone = email, phone

    def set_password_hash(self, password_hash: str) -> None:
        self.password_hash = password_hash

    def assign_role(self, role: Role) -> None:
        self.role = role

    def mark_deleted(self, now: datetime) -> None:
        if self.deleted_at is None:
            self.deleted_at = now
