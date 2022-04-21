from uuid import UUID

from mognet.exceptions.base_exceptions import MognetError


class TooManyRetries(MognetError):
    """
    Raised when a task is retried too many times due to unforeseen errors (e.g., SIGKILL).

    The number of retries for any particular task can be configured through the App's
    configuration, in `max_retries`.
    """

    def __init__(
        self,
        request_id: UUID,
        actual_retries: int,
        max_retries: int,
    ) -> None:
        super().__init__(request_id, actual_retries, max_retries)

        self.request_id = request_id
        self.max_retries = max_retries
        self.actual_retries = actual_retries

    def __str__(self) -> str:
        return f"Task id={self.request_id!r} has been retried {self.actual_retries!r} times, which is more than the limit of {self.max_retries!r}"
