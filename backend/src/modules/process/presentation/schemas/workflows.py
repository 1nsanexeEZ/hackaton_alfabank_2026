from pydantic import BaseModel, ConfigDict


class WorkflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    version: int
    source_hash: str
    nodes: int
    flows: int
