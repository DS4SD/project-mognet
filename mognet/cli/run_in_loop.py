import asyncio
from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar

from typing_extensions import ParamSpec

_P = ParamSpec("_P")
_R = TypeVar("_R")


def run_in_loop(f: Callable[_P, Awaitable[_R]]) -> Callable[_P, _R]:
    """
    Utility to run a click/typer command function in an event loop
    (because they don't support it out of the box)
    """

    @wraps(f)
    def in_loop(*args: Any, **kwargs: Any) -> _R:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(f(*args, **kwargs))

    return in_loop
