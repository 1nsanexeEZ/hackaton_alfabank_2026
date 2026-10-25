"""Integration contracts of all modules. Importing this package fills CONTRACTS."""

from src.core.messaging.contracts import (  # noqa: F401  registers every contract
    applications,
    clients,
    decision,
    enrichment,
    identity,
    market,
    process,
    scoring,
    support,
)
from src.core.messaging.contracts.base import (
    CONTRACTS,
    ContractModel,
    IntegrationMessage,
    get_contract,
)

__all__ = ["CONTRACTS", "ContractModel", "IntegrationMessage", "get_contract"]
