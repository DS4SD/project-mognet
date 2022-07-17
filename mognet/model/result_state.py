from enum import Enum


class ResultState(str, Enum):
    """
    States that a task execution, and its result, can be in.
    """

    # The task associated with this result has not yet started.
    PENDING = "PENDING"

    # The task associated with this result is currently running.
    RUNNING = "RUNNING"

    # The task associated with this result was suspended, either because
    # it yielded subtasks, or because the worker it was on was shut down
    # gracefully.
    SUSPENDED = "SUSPENDED"

    # The task associated with this result finished successfully.
    SUCCESS = "SUCCESS"

    # The task associated with this result failed.
    FAILURE = "FAILURE"

    # The task associated with this result was aborted.
    REVOKED = "REVOKED"

    # Invalid task
    INVALID = "INVALID"

    def __repr__(self) -> str:
        return f"{self.name!r}"


STARTED_STATES = frozenset([ResultState.RUNNING, ResultState.SUSPENDED])

ERROR_STATES = frozenset(
    [ResultState.REVOKED, ResultState.FAILURE, ResultState.INVALID]
)
SUCCESS_STATES = frozenset([ResultState.SUCCESS])

READY_STATES = frozenset(SUCCESS_STATES | ERROR_STATES)
UNREADY_STATES = frozenset([ResultState.PENDING, *STARTED_STATES])

STOPPED_STATES = frozenset([ResultState.SUSPENDED, *READY_STATES])
