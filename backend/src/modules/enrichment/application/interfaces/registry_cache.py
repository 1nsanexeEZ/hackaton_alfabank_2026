"""Кеш разовых просмотров реестра по ИНН."""

from __future__ import annotations

from typing import Protocol

from src.modules.enrichment.application.dto.registry import RegistryExtractDTO


class RegistryCache(Protocol):
    def get(self, inn: str) -> RegistryExtractDTO | None:
        """None — нет в кеше или запись устарела."""
        ...

    def put(self, inn: str, extract: RegistryExtractDTO) -> None: ...
