"""Whether the model answers, without making the status wait for it: a ping to a model
server that is down takes its whole timeout (3 s), the status must answer at once."""

import asyncio
import logging
import time
from collections.abc import Callable

from src.modules.assistant.application.interfaces.language_model import (
    LanguageModel,
    ModelReachability,
)

log = logging.getLogger(__name__)

# The last answer is reused this long; an older one is refreshed in the background.
FRESH_S = 10.0
# The very first status waits this long for the first ping, then answers by rules.
FIRST_WAIT_S = 0.5


class BackgroundModelReachability(ModelReachability):
    def __init__(
        self,
        fresh_s: float = FRESH_S,
        first_wait_s: float = FIRST_WAIT_S,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fresh_s = fresh_s
        self._first_wait_s = first_wait_s
        self._now = now
        # By the model object: tests put another model into the same app.
        self._last: dict[int, tuple[float, bool]] = {}
        self._checks: dict[int, asyncio.Task[bool]] = {}

    async def reachable(self, model: LanguageModel) -> bool:
        key = id(model)
        last = self._last.get(key)
        if last is None or self._now() - last[0] > self._fresh_s:
            self._start(key, model)
        if last is not None:
            return last[1]
        check = self._checks[key]
        done, _ = await asyncio.wait({check}, timeout=self._first_wait_s)
        return check.result() if done else False

    def _start(self, key: int, model: LanguageModel) -> None:
        if key not in self._checks or self._checks[key].done():
            self._checks[key] = asyncio.create_task(self._check(key, model))

    async def _check(self, key: int, model: LanguageModel) -> bool:
        try:
            answer = await model.ping()
        except Exception:
            log.exception("assistant model ping failed")
            answer = False
        self._last[key] = (self._now(), answer)
        return answer
