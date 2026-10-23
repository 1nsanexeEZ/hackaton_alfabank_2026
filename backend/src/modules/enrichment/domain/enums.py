"""Источники обогащения и статусы их ответа."""

from __future__ import annotations

from typing import Literal

Source = Literal["egrul", "fns", "bki", "statement", "gir_bo", "kontur", "bki_head"]
SourceStatus = Literal["ok", "failed", "skipped"]

# Прогноз по выписке строит сам модуль: это не внешний источник, в ok / failed он не считается.
INTERNAL_SOURCES: frozenset[Source] = frozenset({"statement"})
