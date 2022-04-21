from typing import List
from pydantic import BaseModel

from .result import Result


class ResultTree(BaseModel):
    result: "Result"
    children: List["ResultTree"]

    def __str__(self) -> str:
        return f"{self.result.name}(id={self.result.id!r}, state={self.result.state!r}, node_id={self.result.node_id!r})"

    def dict(self, **kwargs):
        return {
            "id": self.result.id,
            "name": self.result.name,
            "state": self.result.state,
            "created": self.result.created,
            "started": self.result.started,
            "finished": self.result.finished,
            "node_id": self.result.node_id,
            "number_of_starts": self.result.number_of_starts,
            "number_of_stops": self.result.number_of_stops,
            "retry_count": self.result.unexpected_retry_count,
            "children": [c.dict() for c in self.children],
        }


ResultTree.update_forward_refs()
