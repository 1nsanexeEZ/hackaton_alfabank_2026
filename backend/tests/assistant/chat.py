"""The assistant through the backend's HTTP API on the S-1…S-8 fixtures: for the
tests (conftest.py) and for the live-model run (evaluate.py)."""

from typing import Any
from uuid import UUID

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from seed.identity import ROLES
from src.core.access.organizations import MemberOrganizationsResolver
from src.core.access.permissions import Permissions
from src.modules.assistant.presentation.dependencies import get_context_source
from src.modules.clients.facade import ClientsFacade
from tests.assistant.fixture_source import FixtureContextSource
from tests.fakes import install
from tests.fakes.clients_facade import FakeClientsFacade
from tests.helpers import bearer, token_for

ROLE_SPECS = {role.name: role for role in ROLES}


def use_fixtures(app: FastAPI) -> FixtureContextSource:
    """The neighbours as the fixtures: applications, decisions, products and the
    demo users' memberships (a user who may sign is a director)."""
    source = FixtureContextSource()
    clients = FakeClientsFacade()
    for account in source.accounts.values():
        role = "director" if account.can_sign else "accountant"
        for organization_id in account.organization_ids:
            clients.add_member(account.account_id, organization_id, role)
    install(app, ClientsFacade, clients)
    install(app, MemberOrganizationsResolver, clients)
    app.dependency_overrides[get_context_source] = lambda: source
    return source


class Chat:
    """A client of the assistant API logged in as a demo user (`data/demo.json`)."""

    def __init__(self, client: TestClient, source: FixtureContextSource) -> None:
        self.client = client
        self.source = source

    def headers(self, user: str, without: tuple[Permissions, ...] = ()) -> dict[str, str]:
        account = self.source.accounts[user]
        spec = ROLE_SPECS[account.role]
        permissions = [p for p in spec.permissions if p not in without]
        policies: dict[Permissions | str, list[str]] = {
            k: [str(p) for p in v] for k, v in spec.policies.items()
        }
        app = self.client.app
        return bearer(token_for(app, permissions, policies, account.account_id))  # type: ignore[arg-type]

    def app_id(self, scenario: str) -> UUID:
        return self.source.scenarios[scenario]

    def start(self, user: str) -> str:
        response = self.client.post("/assistant/conversations", headers=self.headers(user))
        assert response.status_code == 201, response.text
        return str(response.json()["id"])

    def ask(
        self, user: str, text: str, scenario: str | None = None, **extra: str
    ) -> httpx.Response:
        conversation = self.start(user)
        body: dict[str, Any] = {"text": text}
        if scenario:
            body["application_id"] = str(self.app_id(scenario))
        return self.client.post(
            f"/assistant/conversations/{conversation}/messages",
            json=body,
            headers={**self.headers(user), **extra},
        )
