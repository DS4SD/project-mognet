from typing import Any, Dict, List, Tuple, Union

from pydantic import BaseModel
from pydantic.error_wrappers import ValidationError

# Taken from pydantic.error_wrappers
Loc = Tuple[Union[int, str], ...]


class InvalidErrorInfo(BaseModel):
    """Information about a validation error"""

    loc: Loc
    msg: str
    type: str


class Pause(Exception):
    """
    Tasks may raise this when they want to stop
    execution and have their message return to the Task Broker.

    Once the message is retrieved again, task execution will resume.
    """


class InvalidTaskArguments(Exception):
    """
    Raised when the arguments to a task could not be validated.
    """

    def __init__(self, errors: List[InvalidErrorInfo]) -> None:
        super().__init__(errors)
        self.errors = errors

    @classmethod
    def from_validation_error(cls, validation_error: ValidationError):
        return cls([InvalidErrorInfo.parse_obj(e) for e in validation_error.errors()])
