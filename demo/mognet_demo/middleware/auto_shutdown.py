"""
Middleware can be used into hook into several points of the Mognet application, like, for example:

- When tasks start / finish
- When the worker's status changes
- When the app starts or stops

It is therefore a good candidate for tasks like:

- Setting up and cleaning up resources
- Task tracking/logging (e.g., via Sentry)
- Metrics logging (e.g., via StatsD, or Prometheus)
- Etc.
"""

import asyncio
import logging
from typing import TYPE_CHECKING, NoReturn, Optional
from mognet.middleware.middleware import Middleware
from mognet.cli.exceptions import GracefulShutdown

if TYPE_CHECKING:
    from mognet import Result, Context, App

_log = logging.getLogger(__name__)


class AutoShutdownMiddleware(Middleware):
    """
    This middleware allows the Mognet app to shut down
    after some period of inactivity, or when a certain task threshold is reached.

    This is sometimes used by frameworks like Celery to force a reboot of the Worker nodes
    to prevent memory accumulation, either due to memory leaks, or due to Python's memory model.

    This middleware uses the task start/stop events to increment internal counters, and shut down
    the Mognet Worker, when appropriate.
    """

    def __init__(
        self,
        app: "App",
        stop_consuming_after: int = 512,
        shutdown_after_idle: int = 900,
    ) -> None:
        super().__init__()

        self._idle_timeout_s = shutdown_after_idle
        self._max_completed_tasks = stop_consuming_after

        self._current_shutdown_handle = None

        self._completed_task_count = 0

        self._app = app
        self._drain_called = False

    async def on_task_completed(
        self,
        result: "Result",
        context: Optional["Context"] = None,
    ):
        """
        Increment the completed task counter, and stop consuming if the threshold was reached
        """
        self._completed_task_count += 1

        await self._stop_worker_from_consuming()

    async def on_running_task_count_changed(self, running_task_count: int):
        """
        Cancel any existing idle shutdown timers, and reschedule them
        (or just shut down straight) if nothing is currently running on the Mognet Worker.
        """
        self._cancel_current_shutdown_timer()

        if running_task_count > 0:
            return

        if self._drain_called:
            _log.info(
                "All remaining tasks finished on the worker, and worker's consumer stopped, shutting down"
            )

            await self._shutdown()

        if self._idle_timeout_s <= 0:
            return

        _log.debug("Scheduling callback for shutdown")

        loop = asyncio.get_event_loop()

        now = loop.time()

        self._current_shutdown_handle = loop.call_at(
            now + self._idle_timeout_s, self._schedule_shutdown
        )

    def _schedule_shutdown(self):
        return asyncio.create_task(self._shutdown())

    async def _shutdown(self) -> NoReturn:
        _log.warning("Going to shut down!")

        self._current_shutdown_handle = None

        raise GracefulShutdown()

    def _cancel_current_shutdown_timer(self):
        if self._current_shutdown_handle is not None:
            self._current_shutdown_handle.cancel()
            self._current_shutdown_handle = None

    async def _stop_worker_from_consuming(self):
        if self._max_completed_tasks <= 0 or self._drain_called:
            return

        worker = self._app.worker
        if worker is None:
            return

        if self._completed_task_count > self._max_completed_tasks:
            pending_task_count = worker.waiting_task_count

            if pending_task_count > 0:
                _log.warning(
                    "Reach max task count of %r on this node, but it still has %r tasks pending. Not stopping the worker's consumer",
                    self._max_completed_tasks,
                    pending_task_count,
                )
                return

            self._drain_called = True

            _log.warning(
                "Reached max task count of %r on this node. Stopping the worker's consumer",
                self._max_completed_tasks,
            )

            await worker.stop_consuming()
