from pydantic_settings import BaseSettings, SettingsConfigDict


class ApplicationsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APPLICATIONS_", env_file=".env", extra="ignore")

    # external-mocks service (EDO, ABS); empty — signing and payout are simulated in process.
    external_mocks_url: str | None = None
    # How often overdue offers are moved to EXPIRED.
    offer_expiry_interval_seconds: float = 60
    # Archive of contract PDFs: its own bucket with Object Lock; days a file stays locked.
    contracts_bucket: str = "credit-contracts"
    contracts_retention_days: int = 5 * 365
