from __future__ import annotations

from dataclasses import dataclass

from src.enrichment.application.ports import CreditBureauSource, RegistrySource, TaxSource


@dataclass(frozen=True)
class Sources:
    registry: RegistrySource
    tax: TaxSource
    bureau: CreditBureauSource
