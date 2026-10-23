from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkflowDTO:
    """A route loaded at startup, for the back office list."""

    code: str
    version: int
    source_hash: str
    nodes: int
    flows: int
