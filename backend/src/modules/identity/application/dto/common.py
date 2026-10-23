from datetime import datetime
from enum import Enum
from typing import Final, Literal


class _Unset(Enum):
    UNSET = "UNSET"


# A PATCH field that wasn't sent, unlike one sent as null.
UNSET: Final = _Unset.UNSET
Unset = Literal[_Unset.UNSET]


def stored(moment: datetime | None) -> datetime:
    """A timestamp the repository fills once the entity is stored."""
    if moment is None:
        raise RuntimeError("The entity is not stored yet")
    return moment
