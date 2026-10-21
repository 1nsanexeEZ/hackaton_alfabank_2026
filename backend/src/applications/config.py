from pydantic_settings import BaseSettings, SettingsConfigDict


class ApplicationsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APPLICATIONS_", env_file=".env", extra="ignore")

    # external-mocks service (EDO, ABS); empty — signing is simulated in process.
    external_mocks_url: str | None = None
