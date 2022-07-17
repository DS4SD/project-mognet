from __future__ import annotations

import asyncio
import inspect
import logging
from asyncio.futures import Future
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any, AsyncGenerator, Dict, List, Optional, Set
from uuid import UUID

from pydantic import ValidationError
from pydantic.decorator import ValidatedFunction

from mognet.broker.base_broker import IncomingMessagePayload
from mognet.context.context import Context
from mognet.exceptions.task_exceptions import InvalidTaskArguments, Pause
from mognet.exceptions.too_many_retries import TooManyRetries
from mognet.model.result import Result
from mognet.model.result_state import ResultState
from mognet.primitives.request import Request
from mognet.state.state import State
from mognet.tasks.task_registry import UnknownTask
from mognet.tools.backports.aioitertools import as_generated

if TYPE_CHECKING:
    from mognet.app.app import App
    from mognet.middleware.middleware import Middleware

_log = logging.getLogger(__name__)


class MessageCancellationAction(str, Enum):
    NOTHING = "nothing"
    ACK = "ack"
    NACK = "nack"


class Worker:
    """
    Workers are responsible for running the fetch -> run -> store result
    loop, for the task queues that are configured.
    """

    running_tasks: Dict[UUID, _RequestProcessorHolder]

    # Set of tasks that are suspended
    _waiting_tasks: Set[UUID]

    app: "App"

    def __init__(
        self,
        *,
        app: "App",
        middleware: Optional[List["Middleware"]] = None,
    ) -> None:
        self.app = app
        self.running_tasks = {}
        self._waiting_tasks = set()
        self._middleware = middleware or []

        self._current_prefetch = 1

        self._queue_consumption_tasks: List[
            AsyncGenerator[IncomingMessagePayload, None]
        ] = []
        self._consume_task: Optional[asyncio.Task[None]] = None

    async def run(self) -> None:
        _log.debug("Starting worker")

        try:
            self.app.broker.add_connection_failed_callback(self._handle_connection_lost)

            await self.start_consuming()
        except asyncio.CancelledError:
            _log.debug("Stopping run")
            return
        except Exception as exc:  # pylint: disable=broad-except
            _log.error("Error during consumption", exc_info=exc)

    async def _handle_connection_lost(
        self, exc: Optional[BaseException] = None
    ) -> None:
        _log.error("Handling connection lost event, stopping all tasks", exc_info=exc)

        # No point in NACKing, because we have been disconnected
        await self._cancel_all_tasks(message_action=MessageCancellationAction.NOTHING)

    async def _cancel_all_tasks(
        self, *, message_action: MessageCancellationAction
    ) -> None:
        all_req_ids = list(self.running_tasks)

        _log.debug("Cancelling all %r running tasks", len(all_req_ids))

        try:
            for req_id in all_req_ids:
                await self.cancel(req_id, message_action=message_action)

            await self._adjust_prefetch()
        finally:
            self._waiting_tasks.clear()

    async def stop_consuming(self) -> None:
        _log.debug("Closing queue consumption tasks")

        consumers = self._queue_consumption_tasks
        while consumers:
            consumer = consumers.pop(0)

            try:
                await asyncio.wait_for(consumer.aclose(), 5)
            except (asyncio.CancelledError, GeneratorExit, asyncio.TimeoutError):
                pass
            except Exception as consume_exc:  # pylint: disable=broad-except
                _log.debug("Error closing consumer", exc_info=consume_exc)

        consume_task = self._consume_task
        self._consume_task = None

        if consume_task is not None:
            _log.debug("Closing aggregation task")

            try:
                consume_task.cancel()
                await asyncio.wait_for(consume_task, 15)

                _log.debug("Closed consumption task")
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as consume_err:  # pylint: disable=broad-except
                _log.error("Error shutting down consumer task", exc_info=consume_err)

    async def close(self) -> None:
        """
        Stops execution, cancelling all running tasks.
        """

        _log.debug("Closing worker")

        await self.stop_consuming()

        # Cancel and NACK all messages currently on this worker.
        await self._cancel_all_tasks(message_action=MessageCancellationAction.NACK)

        _log.debug("Closed worker")

    def _remove_running_task(self, req_id: UUID) -> Optional[_RequestProcessorHolder]:
        fut = self.running_tasks.pop(req_id, None)

        asyncio.create_task(self._emit_running_task_count_change())

        return fut

    def _add_running_task(self, req_id: UUID, holder: _RequestProcessorHolder) -> None:
        self.running_tasks[req_id] = holder
        asyncio.create_task(self._emit_running_task_count_change())

    async def cancel(
        self, req_id: UUID, *, message_action: MessageCancellationAction
    ) -> None:
        """
        Cancels, if any, the execution of a request.
        Whoever calls this method is responsible for updating the result on the backend
        accordingly.
        """
        fut = self._remove_running_task(req_id)

        if fut is None:
            _log.debug("Request id=%r is not running on this worker", req_id)
            return

        _log.info("Cancelling task %r", req_id)

        result = await self.app.result_backend.get_or_create(req_id)

        # Only suspend the result on the backend if it was running in our node.
        if (
            result.state == ResultState.RUNNING
            and result.node_id == self.app.config.node_id
        ):
            await asyncio.shield(result.suspend())
            _log.debug("Result for task %r suspended", req_id)

        _log.debug("Waiting for coroutine of task %r to finish", req_id)

        # Wait for the task to finish, this allows it to clean up.
        try:
            await asyncio.wait_for(fut.cancel(message_action=message_action), 15)
        except asyncio.TimeoutError:
            _log.warning(
                "Handler for task id=%r took longer than 15s to shut down", req_id
            )
        except Exception as exc:  # pylint: disable=broad-except
            _log.error(
                "Handler for task=%r failed while shutting down", req_id, exc_info=exc
            )

        _log.debug("Stopped handler of task id=%r", req_id)

    def _create_context(self, request: "Request[Any]") -> "Context":
        if not self.app.state_backend:
            raise RuntimeError("No state backend defined")

        return Context(
            self.app,
            request,
            State(self.app, request.id),
            self,
        )

    async def _run_request(self, req: Request[Any]) -> None:
        """
        Processes a request, validating it before running.
        """

        _log.debug("Received request %r", req)

        # Check if we're not trying to (re) start something which is already done,
        # for cases when a request is cancelled before it's started.
        # Even worse, check that we're not trying to start a request whose
        # result might have been evicted.
        res = await self.app.result_backend.get(req.id)

        if res is None:
            _log.error(
                "Attempting to run task %r, but it's result doesn't exist on the backend. Discarding",
                req,
            )
            await self.remove_suspended_task(req.id)
            return

        # Shut up, mypy. 'res' cannot be None after this point.
        result: Result[Any] = res

        context = self._create_context(req)

        if result.done:
            _log.error(
                "Attempting to re-run task %r, when it's already done with state %r. Discarding",
                req,
                result.state,
            )
            return await asyncio.shield(self._on_complete(context, result))

        # Check if we should even start, because:
        # 1. We might be in a crash loop (if the process gets killed without cleanup, the numbers won't match),
        # 2. Infinite recursion
        # 3. We might be part of a parent request that was revoked (or doesn't exist)
        # 4. We might be too late.

        # 1. Too many starts
        retry_count = result.unexpected_retry_count

        if retry_count > 0:
            _log.warning(
                "Task %r has been retried %r times (max=%r)",
                req.id,
                retry_count,
                self.app.config.max_retries,
            )

        if retry_count > self.app.config.max_retries:
            _log.error(
                "Discarding task %r because it has exceeded the maximum retry count of %r",
                req,
                self.app.config.max_retries,
            )

            result = await result.set_error(
                TooManyRetries(req.id, retry_count, self.app.config.max_retries)
            )

            return await asyncio.shield(self._on_complete(context, result))

        if req.stack:

            # 2. Recursion
            if len(req.stack) > self.app.config.max_recursion:
                result = await result.set_error(RecursionError())
                return await asyncio.shield(self._on_complete(context, result))

            # 3. Parent task(s) aborted (or doesn't exist)
            for parent_id in reversed(req.stack):
                parent_result = await self.app.result_backend.get(parent_id)

                if parent_result is None:
                    result = await result.set_error(
                        Exception(f"Parent request id={parent_id} does not exist"),
                        state=ResultState.REVOKED,
                    )
                    return await asyncio.shield(self._on_complete(context, result))

                if parent_result.state == ResultState.REVOKED:
                    result = await result.set_error(
                        Exception(f"Parent request id={parent_result.id} was revoked"),
                        state=ResultState.REVOKED,
                    )
                    return await asyncio.shield(self._on_complete(context, result))

        # 4. Request arrived past the deadline.

        if isinstance(req.deadline, datetime):
            # One cannot compare naive and aware datetime,
            # so create equivalent datetime objects.
            now = datetime.now(tz=req.deadline.tzinfo)

            if req.deadline < now:
                _log.error(
                    "Request %r arrived too late. Deadline is %r, current date is %r. Marking it as REVOKED and discarding",
                    req,
                    req.deadline,
                    now,
                )
                result = await asyncio.shield(
                    result.set_error(asyncio.TimeoutError(), state=ResultState.REVOKED)
                )
                return await asyncio.shield(self._on_complete(context, result))

        # Get the function for the task. Fail if the task is not registered in
        # our app's context.
        try:
            task_function = self.app.task_registry.get_task_function(req.name)
        except UnknownTask as unknown_task:
            _log.error(
                "Request %r is for an unknown task: %r",
                req,
                req.name,
                exc_info=unknown_task,
            )
            result = await result.set_error(unknown_task, state=ResultState.INVALID)
            return await asyncio.shield(self._on_complete(context, result))

        # Mark this as running.
        await result.start(node_id=self.app.config.node_id)

        await asyncio.shield(self._on_starting(context))

        try:
            # Create a validated version of the function.
            # This not only does argument validation, but it also parses the values
            # into objects.
            validated = ValidatedFunction(
                task_function, config=_TaskFuncArgumentValidationConfig
            )

            # This does the model validation part.
            model = validated.init_model_instance(context, *req.args, **req.kwargs)

            if inspect.iscoroutinefunction(task_function):
                fut = validated.execute(model)
            else:
                _log.debug(
                    "Handler for task %r is not a coroutine function, running in the loop's default executor",
                    req.name,
                )

                # Run non-coroutine functions inside an executor.
                # This allows them to run without blocking the event loop
                # (providing the GIL does not block it either)
                fut = self.app.loop.run_in_executor(None, validated.execute, model)

        except ValidationError as exc:
            _log.error(
                "Could not call task function %r because of a validation error",
                task_function,
                exc_info=exc,
            )

            invalid = InvalidTaskArguments.from_validation_error(exc)

            result = await asyncio.shield(
                result.set_error(invalid, state=ResultState.INVALID)
            )

            return await asyncio.shield(self._on_complete(context, result))

        if req.deadline is not None:
            if isinstance(req.deadline, datetime):
                # One cannot compare naive and aware datetime,
                # so create equivalent datetime objects.
                now = datetime.now(tz=req.deadline.tzinfo)
                timeout = (req.deadline - now).total_seconds()
            else:
                timeout = req.deadline.total_seconds()

            _log.debug("Applying %.2fs timeout to request %r", timeout, req)

            fut = asyncio.wait_for(fut, timeout=timeout)

        # Start executing.
        try:
            value = await fut

            if req.id in self.running_tasks:
                result = await asyncio.shield(result.set_result(value))

                _log.info(
                    "Request %r finished with status %r in %.2fs",
                    req,
                    result.state,
                    (result.duration or timedelta()).total_seconds(),
                )

                await asyncio.shield(self._on_complete(context, result))
        except Pause:
            _log.info(
                "Handler for %r requested to be paused. Suspending it on the Result Backend and NACKing the message",
                req,
            )

            holder = self.running_tasks.pop(req.id, None)
            if holder is not None:
                await asyncio.shield(result.suspend())
                await asyncio.shield(holder.message.nack())
        except asyncio.CancelledError:
            _log.debug("Handler for task %r cancelled", req)

            # Re-raise the cancellation, this will be caught in the parent function
            # and prevent ack/nack
            raise
        except Exception as exc:  # pylint: disable=broad-except
            state = ResultState.FAILURE

            # The task's coroutine may raise `asyncio.TimeoutError` itself, so there's
            # no guarantee that the timeout we catch is actually related to the request's timeout.
            # So, this heuristic is not the best.
            # TODO: A way to improve it would be to double-check if the deadline itself is expired.
            if req.deadline is not None and isinstance(exc, asyncio.TimeoutError):
                state = ResultState.REVOKED

            if req.id in self.running_tasks:
                result = await asyncio.shield(result.set_error(exc, state=state))
                await asyncio.shield(self._on_complete(context, result))

            duration = result.duration

            if duration is not None:
                _log.error(
                    "Handler for task %r failed in %.2fs with state %r",
                    req,
                    duration.total_seconds(),
                    state,
                    exc_info=exc,
                )
            else:
                _log.error(
                    "Handler for task %r failed with state %r",
                    req,
                    state,
                    exc_info=exc,
                )

    async def _on_complete(self, context: "Context", result: Result[Any]) -> None:
        if result.done:
            await context.state.clear()

        await self.remove_suspended_task(context.request.id)

        for middleware in self._middleware:
            try:
                _log.debug("Calling 'on_task_completed' middleware: %r", middleware)
                await asyncio.shield(
                    middleware.on_task_completed(result, context=context)
                )
            except Exception as mw_exc:  # pylint: disable=broad-except
                _log.error("Middleware %r failed", middleware, exc_info=mw_exc)

    async def _on_starting(self, context: "Context") -> None:
        _log.info("Starting task %r", context.request)

        for middleware in self._middleware:
            try:
                _log.debug("Calling 'on_task_starting' middleware: %r", middleware)
                await asyncio.shield(middleware.on_task_starting(context))
            except Exception as mw_exc:  # pylint: disable=broad-except
                _log.error("Middleware %r failed", middleware, exc_info=mw_exc)

    def _process_request_message(
        self, payload: IncomingMessagePayload
    ) -> asyncio.Task[None]:
        """
        Creates an asyncio.Task which will process the enclosed Request
        in the background.

        Returns said task, after adding completion handlers to it.
        """
        _log.debug("Parsing input of message id=%r as Request", payload.id)
        req: Request[Any] = Request.parse_obj(payload.payload)

        async def request_processor() -> None:
            try:
                await self._run_request(req)

                _log.debug("ACK message id=%r for request=%r", payload.id, req)
                await asyncio.shield(payload.ack())
            except asyncio.CancelledError:
                _log.debug("Cancelled execution of request=%r", req)
                return
            except Exception as exc:  # pylint: disable=broad-except
                _log.error(
                    "Fatal error processing request=%r, NAK message id=%r",
                    req,
                    payload.id,
                    exc_info=exc,
                )
                await asyncio.shield(payload.nack())

        def on_processing_done(fut: "Future[Any]") -> None:
            self._remove_running_task(req.id)

            exc = fut.exception()

            if exc is not None and not fut.cancelled():
                _log.error("Fatal error processing %r", req, exc_info=exc)
            else:
                _log.debug("Processed %r successfully", req)

        task = asyncio.create_task(request_processor())
        task.add_done_callback(on_processing_done)

        holder = _RequestProcessorHolder(payload, req, task)

        self._add_running_task(req.id, holder)

        return task

    def start_consuming(self) -> asyncio.Task[None]:
        if self._consume_task is not None:
            return self._consume_task

        self._consume_task = asyncio.create_task(self._start_consuming())

        return self._consume_task

    async def _start_consuming(self) -> None:

        queues = self.app.get_task_queue_names()

        _log.info("Going to consume %r queues", len(queues))

        try:
            await self._adjust_prefetch()

            for queue in queues:
                _log.info("Start consuming task queue=%r", queue)
                self._queue_consumption_tasks.append(
                    self.app.broker.consume_tasks(queue)
                )

            async for payload in as_generated(self._queue_consumption_tasks):
                try:
                    if payload.kind == "Request":
                        self._process_request_message(payload)
                    else:
                        raise ValueError(f"Unknown kind={payload.kind!r}")
                except asyncio.CancelledError:
                    break
                except Exception as exc:  # pylint: disable=broad-except
                    _log.error(
                        "Error processing message=%r, discarding it",
                        payload,
                        exc_info=exc,
                    )
                    await asyncio.shield(payload.ack())
        finally:
            _log.debug("Stopped consuming task queues")

    async def add_waiting_task(self, task_id: UUID) -> None:
        self._waiting_tasks.add(task_id)
        await self._adjust_prefetch()

    async def remove_suspended_task(self, task_id: UUID) -> None:
        try:
            self._waiting_tasks.remove(task_id)
        except KeyError:
            pass
        await self._adjust_prefetch()

    @property
    def waiting_task_count(self) -> int:
        return len(self._waiting_tasks)

    async def _emit_running_task_count_change(self) -> None:
        for middleware in self._middleware:
            try:
                _log.debug("Calling 'on_running_task_count_changed' on %r", middleware)
                await middleware.on_running_task_count_changed(len(self.running_tasks))
            except Exception as mw_exc:  # pylint: disable=broad-except
                _log.error(
                    "'on_running_task_count_changed' failed on %r",
                    middleware,
                    exc_info=mw_exc,
                )

    async def _adjust_prefetch(self) -> None:
        if self._consume_task is None:
            _log.debug("Not adjusting prefetch because not consuming the queue")
            return

        minimum_prefetch = self.app.config.minimum_concurrency

        prefetch = self.waiting_task_count + minimum_prefetch

        max_prefetch = self.app.config.maximum_concurrency

        if max_prefetch is not None and prefetch >= max_prefetch:
            _log.error(
                "Maximum prefetch value of %r reached! No more tasks will be fetched on this node",
                max_prefetch,
            )
            prefetch = max_prefetch

        if prefetch == self._current_prefetch:
            _log.debug(
                "Current prefetch is the same as the new prefetch (%r), not adjusting it",
                prefetch,
            )
            return

        _log.debug(
            "Currently have %r tasks suspended waiting for others. Setting prefetch=%r from previous=%r",
            self.waiting_task_count,
            prefetch,
            self._current_prefetch,
        )

        self._current_prefetch = prefetch
        await self.app.broker.set_task_prefetch(self._current_prefetch)


class _TaskFuncArgumentValidationConfig:
    """
    Configuration class used to initialize
    the validators for functions.
    """

    arbitrary_types_allowed = True


class _RequestProcessorHolder:
    """
    Holds references to the task, request, and message,
    that are being executed.

    Allows for cancelling the task and optionally ack-ing
    back the message to the broker.
    """

    def __init__(
        self,
        incoming_message: IncomingMessagePayload,
        request: Request[Any],
        task: asyncio.Task[Any],
    ) -> None:
        self.message = incoming_message
        self.request = request
        self._task: Optional[asyncio.Task[Any]] = task

    async def cancel(self, *, message_action: MessageCancellationAction) -> None:

        try:
            if message_action == MessageCancellationAction.ACK:
                await asyncio.shield(self.message.ack())
            elif message_action == MessageCancellationAction.NACK:
                await asyncio.shield(self.message.nack())
        except Exception as ack_exc:
            _log.error(
                "Could not ack message for request %r",
                self.request,
                exc_info=ack_exc,
            )

        if self._task is not None:
            # Hold a local reference to the task, and destroy the object-level one
            # to prevent multiple cancellations.
            t = self._task
            self._task = None

            t.cancel()

            try:
                await t
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                _log.error("Task handler for %r failed", self.request, exc_info=exc)
