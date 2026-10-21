from typing import Annotated, Protocol

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.facades import FacadeNotRegisteredError, FacadeRegistry, use_facade


class GreeterFacade(Protocol):
    def greet(self) -> str: ...


class Greeter:
    def __init__(self, session: AsyncSession | None) -> None:
        self.session = session

    def greet(self) -> str:
        return "hello"


def test_factory_gets_the_callers_session() -> None:
    registry = FacadeRegistry()
    registry.register(GreeterFacade, Greeter)
    session = object()
    facade = registry.get(GreeterFacade, session)  # type: ignore[arg-type]
    assert isinstance(facade, Greeter) and facade.session is session
    assert registry.has(GreeterFacade)


def test_missing_facade_names_the_fix() -> None:
    with pytest.raises(FacadeNotRegisteredError, match="module.wire"):
        FacadeRegistry().get(GreeterFacade, None)  # type: ignore[arg-type]


def test_use_facade_in_a_route() -> None:
    class _Sessions:
        def __call__(self) -> "_Sessions":
            return self

        async def __aenter__(self) -> str:
            return "session"

        async def __aexit__(self, *args: object) -> None:
            return None

    app = FastAPI()
    app.state.facades = FacadeRegistry()
    app.state.facades.register(GreeterFacade, Greeter)
    app.state.session_factory = _Sessions()

    @app.get("/greet")
    async def greet(
        greeter: Annotated[GreeterFacade, Depends(use_facade(GreeterFacade))],
    ) -> dict[str, str]:
        assert isinstance(greeter, Greeter) and greeter.session == "session"
        return {"text": greeter.greet()}

    with TestClient(app) as client:
        assert client.get("/greet").json() == {"text": "hello"}
