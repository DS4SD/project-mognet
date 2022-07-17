import sys
from typing import TYPE_CHECKING, Any, Optional

from mognet.model.result import Result

if sys.version_info >= (3, 10):
    from typing import Protocol
else:
    from typing_extensions import Protocol


if TYPE_CHECKING:
    from mognet.app.app import App
    from mognet.context.context import Context
    from mognet.model.result import Result
    from mognet.primitives.request import Request


class Middleware:
    """
    Defines middleware that can hook into different parts of a Mognet App's lifecycle.
    """

    async def on_app_starting(self, app: "App") -> None:
        """
        Called when the app is starting, but before it starts connecting to the backends.

        For example, you can use this for some early initialization of singleton-type objects in your app.
        """

    async def on_app_started(self, app: "App") -> None:
        """
        Called when the app has started.

        For example, you can use this for some early initialization of singleton-type objects in your app.
        """

    async def on_app_stopping(self, app: "App") -> None:
        """
        Called when the app is preparing to stop, but before it starts disconnecting.

        For example, you can use this for cleaning up objects that were previously set up.
        """

    async def on_app_stopped(self, app: "App") -> None:
        """
        Called when the app has stopped.

        For example, you can use this for cleaning up objects that were previously set up.
        """

    async def on_task_starting(self, context: "Context") -> None:
        """
        Called when a task is starting.

        You can use this, for example, to track a task on a database.
        """

    async def on_task_completed(
        self, result: "Result[Any]", context: Optional["Context"] = None
    ) -> None:
        """
        Called when a task has completed it's execution.

        You can use this, for example, to track a task on a database.
        """

    async def on_request_submitting(
        self, request: "Request[Any]", context: Optional["Context"] = None
    ) -> None:
        """
        Called when a Request object is going to be submitted to the Broker.

        You can use this, for example, both to track the task on a database, or to modify
        the Request object (e.g., to modify arguments, or set metadata).
        """

    async def on_running_task_count_changed(self, running_task_count: int) -> None:
        """
        Called when the Worker's task count changes.

        This can be used to determine when the Worker has nothing to do.
        """
