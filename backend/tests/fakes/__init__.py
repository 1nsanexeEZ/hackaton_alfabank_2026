"""In-memory fakes of every module facade, plus messaging fakes.

Register a fake on the app before the client starts:

    fake = FakeClientsFacade()
    install(app, ClientsFacade, fake)
    install(app, MemberOrganizationsResolver, fake)  # org_member policy
"""

from typing import Any

from fastapi import FastAPI


def install(app: FastAPI, key: type[Any], fake: Any) -> Any:
    app.state.facades.register(key, lambda _session: fake)
    return fake
