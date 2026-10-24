import asyncio

from fastapi.testclient import TestClient

from src.core.config import Settings
from src.core.domain.clock import FrozenClock
from src.core.facades import FacadeRegistry
from src.core.messaging.runtime import MessagingRuntime
from src.main import MODULES, create_app
from tests.helpers import create_schema


def test_every_module_is_wired() -> None:
    names = [module.NAME for module in MODULES]
    assert names == [
        "identity",
        "products",
        "clients",
        "applications",
        "process",
        "enrichment",
        "scoring",
        "decision",
        "notifications",
        "support",
        "projector",
        "bff",
    ]
    for module in MODULES:
        assert callable(module.register) and callable(module.wire)
        assert isinstance(module.subscribers(), list)


def test_app_starts_with_messaging(client: TestClient) -> None:
    messaging = client.app.state.messaging  # type: ignore[attr-defined]
    assert isinstance(messaging, MessagingRuntime)
    assert messaging.mode == "manual"
    # nothing staged yet: the flow settles in one round
    assert client.portal.call(messaging.drain) == 1  # type: ignore[union-attr]


def test_health_and_ready(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ok", "checks": {"database": "ok"}}


def test_request_id_is_generated(client: TestClient) -> None:
    response = client.get("/health")
    request_id = response.headers["x-request-id"]
    assert len(request_id) == 32


def test_request_id_is_kept_when_sane(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "front-123.abc"})
    assert response.headers["x-request-id"] == "front-123.abc"


def test_request_id_is_replaced_when_unsafe(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "bad id\r\nx: y"})
    assert response.headers["x-request-id"] != "bad id\r\nx: y"
    assert len(response.headers["x-request-id"]) == 32


def test_identity_still_works(client: TestClient, admin_token: str) -> None:
    response = client.get("/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200


def test_messaging_stops_cleanly() -> None:
    # stop() without start() must not hang (lifespan failure path)
    runtime = MessagingRuntime(
        Settings(_env_file=None, messaging_mode="manual"),
        None,  # type: ignore[arg-type]
        FacadeRegistry(),
        FrozenClock(),
        [],
    )
    asyncio.run(runtime.stop())


def test_in_process_mode_starts_and_stops(settings: Settings) -> None:
    in_process = settings.model_copy(update={"messaging_mode": "in_process"})
    create_schema(in_process.database_url)
    with TestClient(create_app(in_process)) as test_client:
        assert test_client.get("/health").status_code == 200


def test_background_jobs_start_and_stop(settings: Settings) -> None:
    with_jobs = settings.model_copy(update={"run_background_jobs": True})
    create_schema(with_jobs.database_url)
    app = create_app(with_jobs)
    with TestClient(app) as test_client:
        assert test_client.get("/health").status_code == 200
        _, task = app.state.applications_jobs
        assert not task.done()
    assert task.done()
