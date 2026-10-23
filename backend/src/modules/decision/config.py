from decimal import Decimal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DecisionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DECISION_", env_file=".env", extra="ignore")

    # Ключевая ставка ЦБ, % годовых. Значение по умолчанию синтетическое и совпадает с опорной
    # ставкой политики (key_rate_reference); на дату сдачи сверить с cbr.ru.
    key_rate: Decimal = Field(default=Decimal("16.50"), ge=0, le=100)

    # Ночной пакет предодобрения (работает при RUN_BACKGROUND_JOBS): раз в интервал пересчитать
    # компании, у которых предложения истекают в ближайшие `pre_approval_refresh_days` дней.
    # Первый проход — с задержкой после старта: сид успевает пересчитать демо-компании сам.
    pre_approval_refresh_interval_seconds: float = Field(default=86_400, gt=0)
    pre_approval_refresh_days: int = Field(default=3, ge=0)
    pre_approval_refresh_first_run_seconds: float = Field(default=60, ge=0)
