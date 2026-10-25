"""Adapters of the language model and the choice between them.

`OpenAICompatibleModel` speaks `POST {base_url}/chat/completions`: Ollama,
llama.cpp server, vLLM, LM Studio, and most model APIs, the bank's own and the
cloud ones. Another protocol is another class with the same `LanguageModel`
interface and one more branch in `build_language_model`.

`local` checks the endpoint before the first request: only hosts next to the
application, closed models refused even if someone points the env at them.
`api` trusts the configured URL: it is the way to plug a provider such as
OpenRouter or a model the bank runs elsewhere; closed models are refused by
name all the same, and the client's own text never goes there.
"""

import logging
import re
from urllib.parse import urlsplit

import httpx

from src.modules.assistant.application.interfaces.language_model import (
    LanguageModel,
    LanguageModelSetup,
    LanguageModelUnavailableError,
)
from src.modules.assistant.domain.prompt import ChatMessage
from src.modules.assistant.infrastructure.adapters.model_gate import GatedLanguageModel
from src.modules.assistant.infrastructure.config import AssistantSettings

log = logging.getLogger(__name__)

# Loading a 4B model from a slow disk on a busy CPU: well over a question's deadline.
WARM_UP_TIMEOUT_S = 300.0

# Hosts where a local model runs next to the application.
DEFAULT_ALLOWED_HOSTS = frozenset(
    {"localhost", "127.0.0.1", "::1", "ollama", "host.docker.internal"}
)
# Paid or closed-model providers: never a `local` model, even if listed as allowed.
BLOCKED_HOST_SUFFIXES = (
    "openai.com",
    "openai.azure.com",
    "anthropic.com",
    "claude.ai",
    "googleapis.com",
    "groq.com",
    "openrouter.ai",
    "together.xyz",
    "together.ai",
    "mistral.ai",
    "deepseek.com",
    "fireworks.ai",
    "perplexity.ai",
    "cohere.ai",
    "cohere.com",
    "x.ai",
    "deepinfra.com",
    "novita.ai",
    "replicate.com",
    "huggingface.co",
    "aliyuncs.com",
    "sberbank.ru",
    "gigachat.ru",
    "yandex.net",
    "yandexcloud.net",
    "api.cloud.yandex.net",
)
# Closed model families: never a `local` model, whatever the host.
BLOCKED_MODEL = re.compile(
    r"gpt-?\d|\bo[134]-|chatgpt|claude|gemini|gigachat|yandexgpt|command-r|grok", re.IGNORECASE
)


class EndpointNotAllowedError(ValueError):
    pass


def check_local_endpoint(base_url: str, model: str, extra_allowed: frozenset[str]) -> None:
    """Raises EndpointNotAllowedError with the reason; called at startup."""
    host = _host(base_url)
    if any(host == s or host.endswith("." + s) for s in BLOCKED_HOST_SUFFIXES):
        raise EndpointNotAllowedError(f"host {host} is a paid or closed-model provider")
    if host not in DEFAULT_ALLOWED_HOSTS and host not in extra_allowed:
        raise EndpointNotAllowedError(
            f"host {host} is not local; add it to ASSISTANT_LLM_EXTRA_ALLOWED_HOSTS if it "
            "serves an open-weights model inside the perimeter, or use the `api` provider"
        )
    if BLOCKED_MODEL.search(model):
        raise EndpointNotAllowedError(f"model {model} is not an open-weights model")


def check_api_endpoint(base_url: str, model: str) -> None:
    """Any host (OpenRouter, the bank's own gateway), but open weights only: a closed
    model is refused by its name, as the case requires."""
    _host(base_url)
    if BLOCKED_MODEL.search(model):
        raise EndpointNotAllowedError(f"model {model} is not an open-weights model")


def _host(base_url: str) -> str:
    parts = urlsplit(base_url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not host:
        raise EndpointNotAllowedError(f"bad ASSISTANT_LLM_BASE_URL: {base_url!r}")
    return host


class OpenAICompatibleModel(LanguageModel):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_s: float,
        *,
        inside_perimeter: bool,
        temperature: float = 0.1,
        max_tokens: int = 400,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self.host = _host(base_url)
        self.inside_perimeter = inside_perimeter
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
            timeout=httpx.Timeout(timeout_s, connect=5.0),
            # Not through the environment's proxy: the address is exactly the configured one.
            trust_env=False,
            transport=transport,
        )

    async def complete(self, messages: list[ChatMessage]) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "stream": False,
        }
        try:
            response = await self._http.post("chat/completions", json=payload)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            raise LanguageModelUnavailableError(type(error).__name__) from error
        if not isinstance(content, str) or not content.strip():
            raise LanguageModelUnavailableError("empty answer")
        return _strip_thinking(content)

    async def ping(self) -> bool:
        """The server answers and has the model: Ollama is up long before the model is pulled."""
        try:
            response = await self._http.get("models", timeout=3.0)
            response.raise_for_status()
            served = {m["id"] for m in response.json()["data"]}
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return False
        # Ollama lists a model pulled without a tag as «name:latest».
        return self.model in served or f"{self.model}:latest" in served

    async def warm_up(self) -> None:
        """One token of an answer: the server loads the model and keeps it for a while.
        A question cut by its deadline makes Ollama drop a half-done load, so the load
        gets its own long one."""
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "Здравствуйте"}],
            "max_tokens": 1,
            "stream": False,
        }
        try:
            response = await self._http.post(
                "chat/completions", json=payload, timeout=httpx.Timeout(WARM_UP_TIMEOUT_S)
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            log.warning("assistant model warm-up failed: %s", type(error).__name__)

    async def aclose(self) -> None:
        await self._http.aclose()


def _strip_thinking(text: str) -> str:
    """Reasoning models may prepend <think>…</think>; the client never sees it."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def build_language_model(
    settings: AssistantSettings, transport: httpx.AsyncBaseTransport | None = None
) -> LanguageModelSetup:
    """The model `ASSISTANT_LLM_PROVIDER` asks for, behind the queue and the deadline.
    A setup that can't be used leaves the assistant on templates, with the reason."""
    provider = settings.llm_provider
    if provider == "off":
        return LanguageModelSetup("off", None, "ASSISTANT_LLM_PROVIDER=off")
    try:
        if provider == "local":
            check_local_endpoint(
                settings.llm_base_url, settings.llm_model, settings.extra_allowed_hosts
            )
        else:
            check_api_endpoint(settings.llm_base_url, settings.llm_model)
    except EndpointNotAllowedError as error:
        log.error("assistant model disabled: %s", error)
        return LanguageModelSetup(provider, None, f"blocked: {error}")
    model = OpenAICompatibleModel(
        settings.llm_base_url,
        settings.llm_api_key,
        settings.llm_model,
        settings.llm_timeout_s,
        inside_perimeter=provider == "local",
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        transport=transport,
    )
    if provider == "api":
        log.warning(
            "assistant model is an external API at %s: answers go there without the "
            "client's own text",
            model.host,
        )
    gated = GatedLanguageModel(
        model, settings.llm_concurrency, settings.llm_max_queue, settings.llm_timeout_s
    )
    return LanguageModelSetup(provider, gated)
