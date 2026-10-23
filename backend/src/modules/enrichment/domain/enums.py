"""Источники обогащения и статусы их ответа."""

from __future__ import annotations

from typing import Literal

# aml — проверка по 115-ФЗ: бенефициары, перечни Росфинмониторинга, ПДЛ, уровень ЗСК.
Source = Literal["egrul", "fns", "bki", "statement", "gir_bo", "kontur", "bki_head", "aml"]
SourceStatus = Literal["ok", "failed", "skipped"]

# Прогноз по выписке строит сам модуль: это не внешний источник, в ok / failed он не считается.
INTERNAL_SOURCES: frozenset[Source] = frozenset({"statement"})
