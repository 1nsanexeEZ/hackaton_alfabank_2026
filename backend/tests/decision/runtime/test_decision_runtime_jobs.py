"""Фоновая задача decision: цикл ночного пакета и его запуск вместе с приложением."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi.testclient import TestClient

from src.core.config import Settings
from src.main import create_app
from src.modules.decision.config import DecisionSettings
from src.modules.decision.jobs import run_pre_approval_refresh
from tests.helpers import create_schema


class _Refresh:
    """Вместо use case: считает проходы, первый может упасть."""

    def __init__(self, fail_first: bool = False) -> None:
        self.calls: list[int] = []
        self.second_pass = asyncio.Event()
        self._fail_first = fail_first

    async def execute(self, within_days: int, batch_size: int = 500) -> int:
        self.calls.append(within_days)
        if len(self.calls) == 2:
            self.second_pass.set()
        if self._fail_first and len(self.calls) == 1:
            raise RuntimeError("clients is down")
        return 1


def _run(refresh: _Refresh, stop: asyncio.Event, **kw: Any) -> asyncio.Task[None]:
    return asyncio.create_task(
        run_pre_approval_refresh(refresh, stop, within_days=3, **kw)  # type: ignore[arg-type]
    )


async def test_runs_every_interval_and_survives_a_failure() -> None:
    refresh = _Refresh(fail_first=True)
    stop = asyncio.Event()
    task = _run(refresh, stop, interval_seconds=0.01)

    await asyncio.wait_for(refresh.second_pass.wait(), timeout=5)
    stop.set()
    await asyncio.wait_for(task, timeout=5)

    assert refresh.calls[:2] == [3, 3]


async def test_stop_before_the_first_run() -> None:
    refresh = _Refresh()
    stop = asyncio.Event()
    task = _run(refresh, stop, interval_seconds=3600, first_run_after_seconds=3600)

    await asyncio.sleep(0)
    stop.set()
    await asyncio.wait_for(task, timeout=5)

    assert refresh.calls == []


def test_settings_defaults() -> None:
    settings = DecisionSettings(_env_file=None)  # type: ignore[call-arg]

    assert settings.pre_approval_refresh_interval_seconds == 86_400
    assert settings.pre_approval_refresh_days == 3


def test_job_starts_and_stops_with_the_app(settings: Settings) -> None:
    with_jobs = settings.model_copy(update={"run_background_jobs": True})
    create_schema(with_jobs.database_url)
    app = create_app(with_jobs)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        _, task = app.state.decision_jobs
        assert not task.done()
    assert task.done() and task.exception() is None


def test_no_job_without_background_jobs(settings: Settings) -> None:
    create_schema(settings.database_url)
    app = create_app(settings)

    with TestClient(app):
        assert not hasattr(app.state, "decision_jobs")
