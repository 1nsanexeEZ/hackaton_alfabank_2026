"""Fake model: answers by a script, records the prompts it got."""

import asyncio
import re
from collections.abc import Callable

from src.modules.assistant.application.interfaces.language_model import (
    LanguageModel,
    LanguageModelUnavailableError,
)
from src.modules.assistant.domain.prompt import ChatMessage

Script = Callable[[list[ChatMessage]], str]


def template_of(messages: list[ChatMessage]) -> str:
    """The template answer from the prompt: what a well-behaved model says."""
    match = re.search(r"Образец ответа[^\n]*\n<<<\n(.*?)\n>>>", messages[-1].content, re.DOTALL)
    assert match, "prompt has no template block"
    return match.group(1)


def context_of(messages: list[ChatMessage]) -> str:
    match = re.search(r"CONTEXT[^\n]*\n<<<\n(.*?)\n>>>", messages[-1].content, re.DOTALL)
    assert match, "prompt has no CONTEXT block"
    return match.group(1)


class FakeLlm(LanguageModel):
    def __init__(
        self,
        script: Script = template_of,
        *,
        fail: bool = False,
        delay_s: float = 0.0,
        reachable: bool = True,
        inside_perimeter: bool = True,
    ) -> None:
        self.model = "fake-open-model"
        self.host = "ollama"
        self.inside_perimeter = inside_perimeter
        self._script = script
        self._fail = fail
        self._delay_s = delay_s
        self._reachable = reachable
        self.calls: list[list[ChatMessage]] = []
        self.warm_ups = 0

    async def complete(self, messages: list[ChatMessage]) -> str:
        self.calls.append(messages)
        if self._delay_s:
            await asyncio.sleep(self._delay_s)
        if self._fail:
            raise LanguageModelUnavailableError("connection refused")
        return self._script(messages)

    async def ping(self) -> bool:
        return self._reachable

    async def warm_up(self) -> None:
        self.warm_ups += 1

    @property
    def prompts(self) -> str:
        return "\n".join(m.content for call in self.calls for m in call)
