from collections.abc import Mapping
from dataclasses import dataclass

from src.modules.identity.domain.exceptions import EmptyNameError

_REQUIRED = ("last_name", "first_name")


@dataclass(slots=True)
class Profile:
    """The person behind an account."""

    last_name: str
    first_name: str
    middle_name: str | None = None
    position: str | None = None

    @property
    def full_name(self) -> str:
        names = (self.last_name, self.first_name, self.middle_name)
        return " ".join(name for name in names if name)

    def apply_changes(self, changes: Mapping[str, str | None]) -> None:
        """Only the given fields change; the last and first name can't be cleared."""
        for field in _REQUIRED:
            if field in changes and changes[field] is None:
                raise EmptyNameError(field)
        for field, value in changes.items():
            setattr(self, field, value)
