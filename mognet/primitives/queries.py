from uuid import UUID, uuid4
from typing import List, Literal
from pydantic import BaseModel, Field


class QueryRequestMessage(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str


class QueryResponseMessage(BaseModel):
    id: UUID = Field(default_factory=uuid4)

    kind: str
    node_id: str
    payload: dict


class StatusResponseMessage(QueryResponseMessage):
    kind: Literal["StatusResponse"] = "StatusResponse"

    class Status(BaseModel):
        running_request_ids: List[UUID]

    payload: Status
