import asyncio
import logging
from asyncio import AbstractEventLoop
from typing import Optional

import aiorun
import typer

from mognet.cli.cli_state import state
from mognet.cli.exceptions import GracefulShutdown

_log = logging.getLogger(__name__)

group = typer.Typer()


@group.callback()
def run(
    include_queues: Optional[str] = typer.Option(
        None,
        metavar="include-queues",
        help="Comma-separated list of the ONLY queues to listen on.",
    ),
    exclude_queues: Optional[str] = typer.Option(
        None,
        metavar="exclude-queues",
        help="Comma-separated list of the ONLY queues to NOT listen on.",
    ),
):
    """Run the app"""

    app = state["app_instance"]

    # Allow overriding the queues this app listens on.
    queues = app.config.task_queues

    if include_queues is not None:
        queues.include = set(q.strip() for q in include_queues.split(","))

    if exclude_queues is not None:
        queues.exclude = set(q.strip() for q in exclude_queues.split(","))

    queues.ensure_valid()

    async def start():
        async with app:
            await app.start()

    async def stop(_: AbstractEventLoop):
        _log.info("Going to close app as part of a shut down")
        await app.close()

    pending_exception_to_raise: BaseException = SystemExit(0)

    def custom_exception_handler(loop: AbstractEventLoop, context: dict):
        """See: https://docs.python.org/3/library/asyncio-eventloop.html#error-handling-api"""

        nonlocal pending_exception_to_raise

        exc = context.get("exception")

        if isinstance(exc, GracefulShutdown):
            _log.debug("Got GracefulShutdown")
        elif isinstance(exc, BaseException):
            pending_exception_to_raise = exc

            _log.error(
                "Unhandled exception; stopping loop: %r %r",
                context.get("message"),
                context,
                exc_info=pending_exception_to_raise,
            )

        loop.stop()

    loop = asyncio.get_event_loop()
    loop.set_exception_handler(custom_exception_handler)

    aiorun.run(
        start(), loop=loop, stop_on_unhandled_errors=False, shutdown_callback=stop
    )

    if pending_exception_to_raise is not None:
        raise pending_exception_to_raise

    return 0
