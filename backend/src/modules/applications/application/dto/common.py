from enum import Enum
from typing import Final, Literal


class _Unset(Enum):
    UNSET = "UNSET"


# A PATCH field that wasn't sent, unlike one sent as null.
UNSET: Final = _Unset.UNSET
Unset = Literal[_Unset.UNSET]
