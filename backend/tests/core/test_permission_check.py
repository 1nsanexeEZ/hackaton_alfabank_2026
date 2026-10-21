from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.core.access.permission_check import ensure_permissions
from src.core.access.permissions import Permissions
from src.core.exceptions.exceptions import PermissionDeniedError
from src.core.schemas.jwt_dto import OpenSubTokenDTO


def token(*permissions: str) -> OpenSubTokenDTO:
    now = datetime.now(UTC)
    return OpenSubTokenDTO(
        subject=uuid4(), permissions=list(permissions), issued_at=now, expires_at=now
    )


def test_granted_permission_passes() -> None:
    ensure_permissions(token("accounts.read"), Permissions.ACCOUNTS_READ)


def test_admin_passes_everything() -> None:
    ensure_permissions(token("admin"), Permissions.ACCOUNTS_DELETE, Permissions.ROLES_CREATE)


def test_missing_permissions_are_listed() -> None:
    with pytest.raises(PermissionDeniedError, match="accounts.create, accounts.delete"):
        ensure_permissions(
            token("accounts.read"),
            Permissions.ACCOUNTS_READ,
            Permissions.ACCOUNTS_DELETE,
            Permissions.ACCOUNTS_CREATE,
        )
