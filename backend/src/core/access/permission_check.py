from src.core.access.permissions import Permissions
from src.core.exceptions.exceptions import PermissionDeniedError
from src.core.schemas.jwt_dto import OpenSubTokenDTO


def ensure_permissions(token: OpenSubTokenDTO, *required: Permissions) -> None:
    granted = set(token.permissions)
    if Permissions.ADMIN.value in granted:
        return
    missing = {p.value for p in required} - granted
    if missing:
        raise PermissionDeniedError(f"Not enough rights: {', '.join(sorted(missing))}")


def has_permissions(token: OpenSubTokenDTO, *required: Permissions) -> bool:
    """The same check without raising: for a right that changes what a request may do."""
    granted = set(token.permissions)
    return Permissions.ADMIN.value in granted or {p.value for p in required} <= granted
