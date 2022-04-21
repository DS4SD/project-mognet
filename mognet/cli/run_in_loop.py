import asyncio
from functools import wraps


def run_in_loop(f):
    """
    Utility to run a click/typer command function in an event loop
    (because they don't support it out of the box)
    """

    @wraps(f)
    def in_loop(*args, **kwargs):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(f(*args, **kwargs))

    return in_loop
