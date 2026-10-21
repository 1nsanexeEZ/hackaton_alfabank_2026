from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.exceptions.exceptions import (
    InfrastructureError,
    InvalidStatusTransitionError,
    NotFoundError,
    ValidationError,
)
from src.core.exceptions.handlers import register_exception_handlers


def make_client() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/validation")
    async def validation() -> None:
        raise ValidationError("Amount is out of range", details={"field": "amount", "max": 5})

    @app.get("/transition")
    async def transition() -> None:
        raise InvalidStatusTransitionError()

    @app.get("/missing")
    async def missing() -> None:
        raise NotFoundError()

    @app.get("/unavailable")
    async def unavailable() -> None:
        raise InfrastructureError()

    return TestClient(app)


def test_details_are_returned_when_given() -> None:
    response = make_client().get("/validation")
    assert response.status_code == 422
    assert response.json() == {
        "code": "validation_error",
        "message": "Amount is out of range",
        "details": {"field": "amount", "max": 5},
    }


def test_no_details_key_without_details() -> None:
    response = make_client().get("/missing")
    assert response.status_code == 404
    assert response.json() == {"code": "not_found", "message": "Not found"}


def test_new_error_types() -> None:
    client = make_client()
    transition = client.get("/transition")
    assert transition.status_code == 409
    assert transition.json()["code"] == "invalid_transition"
    unavailable = client.get("/unavailable")
    assert unavailable.status_code == 503
    assert unavailable.json()["code"] == "unavailable"
