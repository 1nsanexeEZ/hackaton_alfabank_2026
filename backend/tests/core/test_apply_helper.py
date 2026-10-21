from uuid import uuid4

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.core.access.access_context import AccessContext
from src.core.access.apply_helper import apply_access_context, apply_policies
from src.core.access.permissions import Permissions
from src.core.infrastructure.database.mixins import DeletedMixin, OwnableMixin, UUIDPrimaryKeyMixin


class _Base(DeclarativeBase):
    pass


class Credit(UUIDPrimaryKeyMixin, OwnableMixin, DeletedMixin, _Base):
    __tablename__ = "credits_test"
    amount: Mapped[int] = mapped_column()


class Plain(UUIDPrimaryKeyMixin, _Base):
    __tablename__ = "plain_test"


USER_ID = uuid4()
READ = Permissions.CREDITS_READ


def sql(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


def test_applies_every_policy_of_the_permission() -> None:
    stmt = apply_policies(
        select(Credit),
        Credit,
        READ,
        [READ.value],
        {READ.value: ["own_only", "not_deleted"]},
        USER_ID,
    )
    compiled = sql(stmt)
    assert "credits_test.owner_id = " in compiled
    assert USER_ID.hex in compiled.replace("-", "")
    assert "credits_test.deleted_at IS NULL" in compiled


def test_policies_of_other_permissions_are_ignored() -> None:
    stmt = apply_policies(
        select(Credit),
        Credit,
        READ,
        [READ.value, Permissions.CREDITS_UPDATE.value],
        {Permissions.CREDITS_UPDATE.value: ["own_only"]},
        USER_ID,
    )
    assert "WHERE" not in sql(stmt)


def test_admin_is_never_row_restricted() -> None:
    stmt = apply_policies(
        select(Credit),
        Credit,
        READ,
        [Permissions.ADMIN.value],
        {READ.value: ["own_only"]},
        USER_ID,
    )
    assert "WHERE" not in sql(stmt)


@pytest.mark.parametrize(
    "stmt",
    [update(Credit).values(amount=1), delete(Credit)],
    ids=["update", "delete"],
)
def test_update_and_delete_are_narrowed_too(stmt) -> None:
    access = AccessContext(
        user_id=USER_ID,
        permission=READ,
        granted_permissions=[READ.value],
        policies={READ.value: ["own_only"]},
    )
    assert "owner_id = " in sql(apply_access_context(stmt, Credit, access))


@pytest.mark.parametrize("policy", ["own_only", "not_deleted"])
def test_unsupported_policy_fails_loud(policy: str) -> None:
    with pytest.raises(ValueError, match="does not support policy"):
        apply_policies(select(Plain), Plain, READ, [READ.value], {READ.value: [policy]}, USER_ID)


def test_unknown_policy_fails_loud() -> None:
    with pytest.raises(ValueError):
        apply_policies(select(Credit), Credit, READ, [READ.value], {READ.value: ["nope"]}, USER_ID)
