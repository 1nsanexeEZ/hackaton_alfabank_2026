"""The status does not wait for a model server that is down: the ping runs in the background."""

import asyncio
import time
from typing import Any

from src.modules.assistant.infrastructure.adapters.model_status import (
    BackgroundModelReachability,
)


class _Model:
    model = "m"
    host = "h"
    inside_perimeter = True

    def __init__(self, answer: bool, delay: float = 0.0) -> None:
        self.answer = answer
        self.delay = delay
        self.pings = 0

    async def ping(self) -> bool:
        self.pings += 1
        await asyncio.sleep(self.delay)
        return self.answer

    async def complete(self, messages: Any) -> str:
        return ""

    async def warm_up(self) -> None:
        return None


async def test_a_quick_server_answers_on_the_first_status() -> None:
    reachability = BackgroundModelReachability()
    model = _Model(True)
    assert await reachability.reachable(model) is True
    assert await reachability.reachable(model) is True
    assert model.pings == 1  # the answer is reused while fresh


async def test_a_slow_server_does_not_hold_the_status() -> None:
    reachability = BackgroundModelReachability(first_wait_s=0.05)
    model = _Model(True, delay=0.3)
    started = time.monotonic()
    assert await reachability.reachable(model) is False
    assert time.monotonic() - started < 0.25
    await asyncio.sleep(0.4)
    assert await reachability.reachable(model) is True


async def test_an_old_answer_is_refreshed_in_the_background() -> None:
    clock = [0.0]
    reachability = BackgroundModelReachability(fresh_s=10, now=lambda: clock[0])
    model = _Model(True)
    assert await reachability.reachable(model) is True
    model.answer = False
    clock[0] = 11
    # The stale answer goes out at once, the check runs behind it.
    assert await reachability.reachable(model) is True
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert await reachability.reachable(model) is False
    assert model.pings == 2
