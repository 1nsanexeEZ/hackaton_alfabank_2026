"""Keeping the CPU alive: one or two generations at a time, a short queue and a
deadline in front of any model. A local model that missed the deadline is
loaded again in the background, so the next question finds it in memory."""

import asyncio
import logging

from src.modules.assistant.application.interfaces.language_model import (
    LanguageModel,
    LanguageModelBusyError,
    LanguageModelTimeoutError,
)
from src.modules.assistant.domain.prompt import ChatMessage

log = logging.getLogger(__name__)


class GatedLanguageModel(LanguageModel):
    def __init__(
        self, inner: LanguageModel, concurrency: int, max_queue: int, timeout_s: float
    ) -> None:
        self.inner = inner
        self.model = inner.model
        self.host = inner.host
        self.inside_perimeter = inner.inside_perimeter
        self._semaphore = asyncio.Semaphore(concurrency)
        self._max_waiting = concurrency + max_queue
        self._waiting = 0
        self._timeout_s = timeout_s
        self._warming: asyncio.Task[None] | None = None

    async def complete(self, messages: list[ChatMessage]) -> str:
        """Busy at once when the queue is full; the deadline covers the queue too."""
        if self._waiting >= self._max_waiting:
            raise LanguageModelBusyError
        self._waiting += 1
        try:
            async with asyncio.timeout(self._timeout_s):
                async with self._semaphore:
                    return await self.inner.complete(messages)
        except TimeoutError:
            if self.inside_perimeter:
                # Likely a cold start the deadline cut short: load the model meanwhile.
                self.start_warm_up()
            raise LanguageModelTimeoutError from None
        finally:
            self._waiting -= 1

    async def ping(self) -> bool:
        return await self.inner.ping()

    async def warm_up(self) -> None:
        self.start_warm_up()
        if self._warming is not None:
            await asyncio.shield(self._warming)

    def start_warm_up(self) -> None:
        """One load at a time; a second call while it runs does nothing."""
        if self._warming is None or self._warming.done():
            log.info("assistant model warm-up started")
            self._warming = asyncio.create_task(self.inner.warm_up(), name="assistant-warm-up")

    async def aclose(self) -> None:
        if self._warming is not None and not self._warming.done():
            self._warming.cancel()
        close = getattr(self.inner, "aclose", None)
        if close is not None:
            await close()


async def warm_up_when_served(model: LanguageModel, stop: asyncio.Event, retry_s: float) -> None:
    """On startup: wait until the server serves the model (Ollama may still be starting,
    the model may not be pulled yet), then load it once."""
    while not stop.is_set():
        if await model.ping():
            await model.warm_up()
            return
        try:
            await asyncio.wait_for(stop.wait(), timeout=retry_s)
        except TimeoutError:
            continue
