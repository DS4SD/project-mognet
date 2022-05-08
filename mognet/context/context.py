import asyncio
import inspect
import logging
import sys
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Coroutine,
    Dict,
    List,
    Set,
    Type,
    TypeVar,
    Union,
    cast,
    overload,
)

if sys.version_info >= (3, 10):
    from typing import Concatenate, ParamSpec
else:
    from typing_extensions import ParamSpec, Concatenate

from uuid import UUID

from mognet.exceptions.result_exceptions import ResultLost
from mognet.model.result import ResultState
from mognet.primitives.request import Request
from mognet.service.class_service import ClassService

_Return = TypeVar("_Return")

if TYPE_CHECKING:
    from mognet.app.app import App
    from mognet.model.result import Result
    from mognet.state.state import State
    from mognet.worker.worker import Worker

_log = logging.getLogger(__name__)

_P = ParamSpec("_P")


class Context:
    """
    Context for a request.

    Allows access to the App instance, task state,
    and the request that is part of this task execution.
    """

    app: "App"

    state: "State"

    request: "Request"

    _dependencies: Set[UUID]

    def __init__(
        self,
        app: "App",
        request: "Request",
        state: "State",
        worker: "Worker",
    ):
        self.app = app
        self.state = state
        self.request = request
        self._worker = worker

        self._dependencies = set()

        self.create_request = self.app.create_request

    async def submit(self, request: "Request"):
        """
        Submits a new request as part of this one.

        The difference from this method to the one defined in the `App` class
        is that this one will submit the new request as a child request of
        the one that's a part of this `Context` instance. This allows
        the subrequests to be cancelled if the parent is also cancelled.
        """
        return await self.app.submit(request, self)

    @overload
    async def run(self, request: Request[_Return]) -> _Return:
        """
        Submits a Request to be run as part of this one (see `submit`), and waits for the result
        """
        ...

    @overload
    async def run(
        self,
        request: Callable[Concatenate["Context", _P], _Return],
        *args: _P.args,
        **kwargs: _P.kwargs,
    ) -> _Return:
        """
        Short-hand method for creating a Request from a function decorated with `@task`,
        (see `create_request`), submitting it (see `submit`) and waiting for the result (see `run(Request)`).

        This overload is for documenting non-async def functions.
        """
        ...

    # This overload unwraps the Awaitable object
    @overload
    async def run(
        self,
        request: Callable[Concatenate["Context", _P], Awaitable[_Return]],
        *args: _P.args,
        **kwargs: _P.kwargs,
    ) -> _Return:
        """
        Short-hand method for creating a Request from a function decorated with `@task`,
        (see `create_request`), submitting it (see `submit`) and waiting for the result (see `run(Request)`).

        This overload is for documenting async def functions.
        """
        ...

    async def run(self, request, *args, **kwargs):
        """
        Submits and runs a new request as part of this one.

        See `submit` for the difference between this and the equivalent
        `run` method on the `App` class.
        """

        if not isinstance(request, Request):
            request = self.create_request(request, *args, **kwargs)

        cancelled = False
        try:
            had_dependencies = bool(self._dependencies)

            self._dependencies.add(request.id)

            # If we transition from having no dependencies
            # to having some, then we should suspend.
            if not had_dependencies and self._dependencies:
                await asyncio.shield(self._suspend())

            self._log_dependencies()

            return await self.app.run(request, self)
        except asyncio.CancelledError:
            cancelled = True
        finally:
            self._dependencies.remove(request.id)

            self._log_dependencies()

            if not self._dependencies and not cancelled:
                await asyncio.shield(self._resume())

    def _log_dependencies(self):
        _log.debug(
            "Task %r is waiting on %r dependencies",
            self.request,
            len(self._dependencies),
        )

    async def gather(
        self, *results_or_ids: Union["Result", UUID], return_exceptions: bool = False
    ) -> List[Any]:
        results = []
        cancelled = False
        try:
            for result in results_or_ids:
                if isinstance(result, UUID):
                    result = await self.app.result_backend.get(result)

                results.append(result)

            # If we transition from having no dependencies
            # to having some, then we should suspend.
            had_dependencies = bool(self._dependencies)
            self._dependencies.update(r.id for r in results)

            self._log_dependencies()

            if not had_dependencies and self._dependencies:
                await asyncio.shield(self._suspend())

            return await asyncio.gather(*results, return_exceptions=return_exceptions)
        except asyncio.CancelledError:
            cancelled = True
            raise
        finally:
            self._dependencies.difference_update(r.id for r in results)

            self._log_dependencies()

            if not self._dependencies and not cancelled:
                await asyncio.shield(self._resume())

    @overload
    def get_service(
        self, func: Type[ClassService[_Return]], *args, **kwargs
    ) -> _Return:
        ...

    @overload
    def get_service(
        self,
        func: Callable[Concatenate["Context", _P], _Return],
        *args: _P.args,
        **kwargs: _P.kwargs,
    ) -> _Return:
        ...

    def get_service(self, func, *args, **kwargs):
        """
        Get a service to use in the task function.
        This can be used for dependency injection purposes.
        """

        if inspect.isclass(func) and issubclass(func, ClassService):
            if func not in self.app.services:
                # This cast() is only here to silence Pylance (because it thinks the class is abstract)
                instance: ClassService = cast(Any, func)(self.app.config)
                self.app.services[func] = instance.__enter__()

            svc = self.app.services[func]
        else:
            svc = self.app.services.setdefault(func, func)

        return svc(self, *args, **kwargs)

    async def _suspend(self):
        _log.debug("Suspending %r", self.request)

        result = await self.get_result()

        if result.state == ResultState.RUNNING:
            await result.suspend()

        await self._worker.add_waiting_task(self.request.id)

    async def get_result(self):
        """
        Gets the Result associated with this task.

        WARNING: Do not `await` the returned Result instance! You will run
        into a deadlock (you will be awaiting yourself)
        """
        result = await self.app.result_backend.get(self.request.id)

        if result is None:
            raise ResultLost(self.request.id)

        return result

    def call_threadsafe(self, coro: Awaitable[_Return]) -> _Return:
        """
        NOTE: ONLY TO BE USED WITH SYNC TASKS!

        Utility function that will run the coroutine in the app's event loop
        in a thread-safe way.

        In reality this is a wrapper for `asyncio.run_coroutine_threadsafe(...)`

        Use as follows:

        ```
        context.call_sync(context.submit(...))
        ```
        """
        return asyncio.run_coroutine_threadsafe(coro, loop=self.app.loop).result()

    async def set_metadata(self, **kwargs: Any):
        """
        Update metadata on the Result associated with the current task.
        """

        result = await self.get_result()
        return await result.set_metadata(**kwargs)

    async def _resume(self):
        _log.debug("Resuming %r", self.request)

        result = await self.get_result()

        if result.state == ResultState.SUSPENDED:
            await result.resume()

        await self._worker.remove_suspended_task(self.request.id)
