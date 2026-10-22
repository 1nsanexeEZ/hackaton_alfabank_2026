from pydantic_settings import BaseSettings, SettingsConfigDict


class EnrichmentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ENRICHMENT_", env_file=".env", extra="ignore")

    mocks_base_url: str = "http://external-mocks:8100"
    source_timeout_seconds: float = 3.0
    # Backoff before retrying a source on timeout or 5xx: 0.5 → 1 → 2 s (3 attempts total).
    retries: int = 3
