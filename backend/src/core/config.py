from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Smart credit cabinet"
    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/app"

    jwt_issuer: str = "identity"
    jwt_audience: str = "credit-cabinet"
    jwt_access_ttl_minutes: int = 30
    jwt_private_key_path: Path = Path("keys/jwt_private.pem")
    jwt_public_key_path: Path = Path("keys/jwt_public.pem")
    # Generate an RSA key pair on startup when the files are missing (local runs, docker volume).
    jwt_generate_keys: bool = True

    # Idempotently creates the `admin` role and this account on startup, so the
    # very first user can log in and create the rest through the API.
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
