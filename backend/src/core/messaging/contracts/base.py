from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

CONTRACTS: dict[str, type["IntegrationMessage"]] = {}


class ContractModel(BaseModel):
    """Nested part of a contract (offer terms, requested info...)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class IntegrationMessage(ContractModel):
    """Public contract of an event or a command between modules.

    Subclasses declare TYPE (unique name) and TOPIC; they are registered in
    CONTRACTS automatically, consumers use the registry to parse payloads.
    Add fields only with defaults; renaming or removing a field is a breaking
    change that needs a new SCHEMA_VERSION and agreement of all consumers.
    """

    TYPE: ClassVar[str]
    TOPIC: ClassVar[str]
    SCHEMA_VERSION: ClassVar[int] = 1

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "TYPE" not in cls.__dict__:
            return
        if cls.TYPE in CONTRACTS:
            raise TypeError(f"Duplicate integration contract type {cls.TYPE!r}")
        CONTRACTS[cls.TYPE] = cls


def get_contract(message_type: str) -> type[IntegrationMessage]:
    try:
        return CONTRACTS[message_type]
    except KeyError:
        raise LookupError(f"Unknown integration message type {message_type!r}") from None
