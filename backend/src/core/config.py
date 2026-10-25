from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
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

    # kafka — real broker (docker compose); in_process — the same handlers are
    # driven by a background loop without a broker (local runs); manual — nothing
    # runs by itself, tests call app.state.messaging.drain().
    messaging_mode: Literal["kafka", "in_process", "manual"] = "in_process"
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_partitions: int = 3
    kafka_create_topics: bool = True
    outbox_batch_size: int = 100

    minio_endpoint: str = "http://localhost:9000"
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin"
    minio_bucket_name: str = "credit-documents"
    # What the browser sees (presigned URLs go through nginx); None — minio_endpoint.
    minio_public_endpoint: str | None = None
    # Create the bucket on startup; off in tests (no MinIO there).
    minio_ensure_bucket: bool = True

    # Periodic jobs of modules (offer expiry...); off in tests, they call jobs directly.
    run_background_jobs: bool = True

    # The Bank of Russia key rate, % per year: the funding part of the offered rate. Check it
    # against cbr.ru (14.00 — the decision of 23.10.2026).
    key_rate: Decimal = Field(default=Decimal("14.00"), ge=0, le=100)
    # The key rate the catalog rates are set at (seeds, admin). Clients get the rate range and
    # the support program cap moved by key_rate − catalog_key_rate.
    catalog_key_rate: Decimal = Field(default=Decimal("16.50"), ge=0, le=100)

    # Demo organizations, accounts and products from docs (idempotent).
    seed_demo_data: bool = False
    demo_password: str = "Demo-2026!"
    # POST /auth/demo-login: a token for a demo account without a password.
    # For local checks only, keep it off on a public stand.
    demo_login_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
