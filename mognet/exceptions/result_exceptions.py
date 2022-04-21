from mognet.exceptions.base_exceptions import MognetError
from typing import TYPE_CHECKING
from uuid import UUID


if TYPE_CHECKING:
    from mognet.model.result import Result


class ResultError(MognetError):
    pass


class ResultNotReady(ResultError):
    pass


class ResultFailed(ResultError):
    def __init__(self, result: "Result") -> None:
        super().__init__(result)
        self.result = result

    def __str__(self) -> str:
        return f"Result {self.result!r} failed with state {self.result.state!r}"


class Revoked(ResultFailed):
    """Raised when a task is revoked, either by timing out, or manual revoking."""

    def __str__(self) -> str:
        return f"Result {self.result!r} was revoked"


class ResultValueLost(ResultError):
    """
    Raised when the value for a result was lost
    (potentially due to key eviction)
    """

    def __init__(self, result_id: UUID) -> None:
        super().__init__(result_id)
        self.result_id = result_id

    def __str__(self) -> str:
        return f"Value for result id={self.result_id!r} lost"


class ResultLost(ResultError):
    """
    Raised when the result itself was lost
    (potentially due to key eviction)
    """

    def __init__(self, result_id: UUID) -> None:
        super().__init__(result_id)
        self.result_id = result_id

    def __str__(self) -> str:
        return f"Result id={self.result_id!r} lost"
