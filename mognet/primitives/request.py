from datetime import datetime, timedelta
from typing import Any, Dict, Generic, List, Optional, Tuple, Type, TypeVar, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, conint
from pydantic.fields import Field
from typing_extensions import TypeAlias

TReturn = TypeVar("TReturn")

Priority: TypeAlias = conint(ge=0, le=10)  # type: ignore


class Request(BaseModel, Generic[TReturn]):
    id: UUID = Field(default_factory=uuid4)
    name: str

    args: Tuple[Any, ...] = ()
    kwargs: Dict[str, Any] = Field(default_factory=dict)

    stack: List[UUID] = Field(default_factory=list)

    # Metadata that's going to be put in the Result associated
    # with this Request.
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Deadline to run this request.
    # If it's a datetime, the deadline will be computed based on the difference
    # to `datetime.now(tz=timezone.utc)`. If the deadline is already passed, the task
    # is discarded and marked as `REVOKED`.
    # If it's a timedelta, the task's coroutine will be given that long to run, after which
    # it will be cancelled and marked as `REVOKED`.
    # Note that, like with manual revoking, there is no guarantee that the timed out task will
    # actually stop running.
    deadline: Optional[Union[timedelta, datetime]] = None

    # Overrides the queue the message will be sent to.
    queue_name: Optional[str] = None

    # Allow setting a kwargs representation for debugging purposes.
    # This is stored on the corresponding Result.
    # If not set, it's set when the request is submitted.
    # Note that if there are arguments which contain sensitive data, this will leak their values,
    # so you are responsible for ensuring such values are censored.
    kwargs_repr: Optional[str] = None

    # Task priority. The higher the value, the higher the priority.
    priority: Priority = 5

    def __repr__(self) -> str:
        msg = f"{self.name}[id={self.id!r}]"

        if self.kwargs_repr is not None:
            msg += f"({self.kwargs_repr})"

        return msg
