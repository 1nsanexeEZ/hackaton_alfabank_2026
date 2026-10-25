from pydantic_settings import BaseSettings, SettingsConfigDict

from src.modules.assistant.application.interfaces.language_model import Provider


class AssistantSettings(BaseSettings):
    """The model behind the assistant (docs/ai.md).

    off   — no model: answers by templates from the same facts;
    local — an open-weights model inside the perimeter (Ollama, llama.cpp, vLLM):
            only local hosts, closed models refused, the client's own text allowed;
    api   — any OpenAI-compatible API (the bank's own model, a cloud provider):
            the host is not checked, the client's own text never leaves.
    """

    model_config = SettingsConfigDict(env_prefix="ASSISTANT_", env_file=".env", extra="ignore")

    llm_provider: Provider = "off"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = ""
    llm_model: str = "qwen3:4b-instruct-2507-q4_K_M"
    # The whole wait for an answer, the queue included.
    llm_timeout_s: float = 25.0
    # Generations at once and how many may wait on top: a CPU serves one at a time.
    llm_concurrency: int = 1
    llm_max_queue: int = 4
    llm_temperature: float = 0.1
    llm_max_tokens: int = 400
    # `local` only: hosts besides localhost, ollama and host.docker.internal, comma separated.
    llm_extra_allowed_hosts: str = ""
    rate_limit_per_minute: int = 10

    @property
    def extra_allowed_hosts(self) -> frozenset[str]:
        return frozenset(
            h.strip().lower() for h in self.llm_extra_allowed_hosts.split(",") if h.strip()
        )
