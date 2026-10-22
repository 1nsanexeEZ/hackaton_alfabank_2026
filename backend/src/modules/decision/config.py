from decimal import Decimal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DecisionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DECISION_", env_file=".env", extra="ignore")

    # Ключевая ставка ЦБ, % годовых. Значение по умолчанию синтетическое и совпадает с опорной
    # ставкой политики (key_rate_reference); на дату сдачи сверить с cbr.ru.
    key_rate: Decimal = Field(default=Decimal("16.50"), ge=0, le=100)
