import asyncio
import importlib
import logging
import sys
import uuid
from asyncio.futures import Future
from datetime import datetime, timezone
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncGenerator,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    TypeVar,
    Union,
    cast,
    overload,
)

from aio_pika.tools import shield
from mognet.backend.base_result_backend import BaseResultBackend
from mognet.backend.redis_result_backend import RedisResultBackend
from mognet.broker.amqp_broker import AmqpBroker
from mognet.broker.base_broker import (
    BaseBroker,
    IncomingMessagePayload,
    MessagePayload,
    TaskQueue,
)
from mognet.context.context import Context
from mognet.exceptions.base_exceptions import CouldNotSubmit, ImproperlyConfigured
from mognet.middleware.middleware import Middleware
from mognet.model.result import Result, ResultState
from mognet.primitives.queries import QueryRequestMessage, StatusResponseMessage
from mognet.primitives.request import Request
from mognet.primitives.revoke import Revoke
from mognet.service.class_service import ClassService
from mognet.state.base_state_backend import BaseStateBackend
from mognet.state.redis_state_backend import RedisStateBackend
from mognet.tasks.task_registry import TaskRegistry, task_registry
from mognet.tools.kwargs_repr import format_kwargs_repr
from mognet.worker.worker import MessageCancellationAction, Worker

if sys.version_info >= (3, 10):
    from typing import ParamSpec, Concatenate
else:
    from typing_extensions import ParamSpec, Concatenate


if TYPE_CHECKING:
    from mognet.app.app_config import AppConfig

_log = logging.getLogger(__name__)

_P = ParamSpec("_P")
_Return = TypeVar("_Return")


class App:
    """
    Represents the Mognet application.

    You can use these objects to:

    - Create and abort tasks
    - Check the status of tasks
    - Configure the middleware that runs on key lifecycle events of the app and its tasks
    """

    # Where results are stored.
    result_backend: BaseResultBackend

    # Where task state is stored.
    # Task state is information that a task can save
    # during its execution, in case, for example, it gets
    # interrupted.
    state_backend: BaseStateBackend

    # Task broker.
    broker: BaseBroker

    # Mapping of [service name] -> dependency object,
    # should be accessed via Context#get_service.
    services: Dict[Any, Callable]

    # Holds references to all the tasks.
    task_registry: TaskRegistry

    _connected: bool

    # Configuration used to start this app.
    config: "AppConfig"

    # Worker running in this app instance.
    worker: Optional[Worker]

    # Background tasks spawned by this app.
    _consume_control_task: Optional[Future] = None
    _heartbeat_task: Optional[Future] = None

    _worker_task: Optional[Future]

    _middleware: List[Middleware]

    _loop: asyncio.AbstractEventLoop

    def __init__(
        self,
        *,
        name: str,
        config: "AppConfig",
    ) -> None:
        self.name = name

        self._connected = False

        self.config = config

        # Create the task registry and register it globally
        reg = task_registry.get(None)

        if reg is None:
            reg = TaskRegistry()
            reg.register_globally()

        self.task_registry = reg

        self._worker_task = None

        self.services = {}

        self._middleware = []

        self._load_modules()
        self.worker = None

        # Event that gets set when the app is closed
        self._run_result = None

    def add_middleware(self, mw_inst: Middleware):
        """
        Adds middleware to this app.

        Middleware is called in the order of in which it was added
        to the app.
        """
        if mw_inst in self._middleware:
            return

        self._middleware.append(mw_inst)

    async def start(self):
        """
        Starts the app.
        """
        _log.info("Starting app %r", self.config.node_id)

        self._loop = asyncio.get_event_loop()

        self._run_result = asyncio.Future()

        self._log_tasks_and_queues()

        await self._call_on_starting_middleware()

        await self.connect()

        self._heartbeat_task = asyncio.create_task(self._background_heartbeat())
        self._consume_control_task = asyncio.create_task(self._consume_control_queue())

        self.worker = Worker(app=self, middleware=self._middleware)
        self._worker_task = asyncio.create_task(self.worker.run())

        _log.info("Started")

        await self._call_on_started_middleware()

        return await self._run_result

    async def get_current_status_of_nodes(
        self,
    ) -> AsyncGenerator[StatusResponseMessage, None]:
        """
        Query all nodes of this App and get their status.
        """

        request = QueryRequestMessage(name="Status")

        responses = self.broker.send_query_message(
            payload=MessagePayload(
                id=str(request.id),
                kind="Query",
                payload=request.model_dump(),
            )
        )

        try:
            async for response in responses:
                try:
                    yield StatusResponseMessage.model_validate(response)
                except asyncio.CancelledError:
                    break
                except Exception as exc:  # pylint: disable=broad-except
                    _log.error(
                        "Could not parse status response %r", response, exc_info=exc
                    )
        finally:
            await responses.aclose()

    async def submit(self, req: "Request", context: Optional[Context] = None) -> Result:
        """
        Submits a request for execution.

        If a context is defined, it will be used to create a parent-child
        relationship between the new-to-submit request and the one existing
        in the context instance. This is later used to cancel the whole task tree.
        """
        if not self.result_backend:
            raise ImproperlyConfigured("Result backend not defined")

        if not self.broker:
            raise ImproperlyConfigured("Broker not connected")

        try:
            if req.kwargs_repr is None:
                req.kwargs_repr = format_kwargs_repr(req.args, req.kwargs)
                _log.debug("Set default kwargs_repr on Request %r", req)

            res = Result(
                self.result_backend,
                id=req.id,
                name=req.name,
                state=ResultState.PENDING,
                created=datetime.now(tz=timezone.utc),
                request_kwargs_repr=req.kwargs_repr,
            )

            if context is not None:
                # Set the parent-child relationship and update the request stack.
                parent_request = context.request
                res.parent_id = parent_request.id

                req.stack = [*parent_request.stack, parent_request.id]

                if res.parent_id is not None:
                    await self.result_backend.add_children(res.parent_id, req.id)

            await self.result_backend.set(req.id, res)

            # Store the metadata on the Result.
            if req.metadata:
                await res.set_metadata(**req.metadata)

            await self._on_submitting(req, context=context)

            payload = MessagePayload(
                id=str(req.id),
                kind="Request",
                payload=req.model_dump(),
                priority=req.priority,
            )

            _log.debug("Sending message %r", payload.id)

            await self.broker.send_task_message(self._get_task_route(req), payload)

            return res
        except Exception as exc:
            raise CouldNotSubmit(f"Could not submit {req!r}") from exc

    def get_task_queue_names(self) -> Set[str]:
        """
        Return the names of the queues that are going to be consumed,
        after applying defaults, inclusions, and exclusions.
        """
        all_queues = {*self.config.task_routes.values(), self.config.default_task_route}

        _log.debug("All queues: %r", all_queues)

        configured_queues = self.config.task_queues

        configured_queues.ensure_valid()

        if configured_queues.exclude:
            _log.debug("Applying queue exclusions: %r", configured_queues.exclude)
            return all_queues - configured_queues.exclude

        if configured_queues.include:
            _log.debug("Applying queue inclusions: %r", configured_queues.include)
            return all_queues & configured_queues.include

        _log.debug("No inclusions or exclusions applied")

        return all_queues

    @overload
    def create_request(
        self,
        func: Callable[Concatenate["Context", _P], Awaitable[_Return]],
        *args: _P.args,
        **kwargs: _P.kwargs,
    ) -> Request[_Return]:
        """
        Creates a Request object from the function that was decorated with @task,
        and the provided arguments.

        This overload is just to document async def function return values.
        """
        ...

    @overload
    def create_request(
        self,
        func: Callable[Concatenate["Context", _P], _Return],
        *args: _P.args,
        **kwargs: _P.kwargs,
    ) -> Request[_Return]:
        """
        Creates a Request object from the function that was decorated with @task,
        and the provided arguments.

        This overload is just to document non-async def function return values.
        """
        ...

    def create_request(
        self,
        func: Callable[Concatenate["Context", _P], Any],
        *args: _P.args,
        **kwargs: _P.kwargs,
    ) -> Request:
        """
        Creates a Request object from the function that was decorated with @task,
        and the provided arguments.
        """
        return Request(
            name=self.task_registry.get_task_name(cast(Any, func)),
            args=args,
            kwargs=kwargs,
        )

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
        """
        ...

    @overload
    async def run(
        self, request: "Request[_Return]", context: Optional[Context] = None
    ) -> _Return:
        """
        Runs the request and waits for the result.

        Call `submit` if you just want to send a request
        without waiting for the result.
        """

        ...

    async def run(self, request, *args, **kwargs) -> Any:

        if not isinstance(request, Request):
            request = self.create_request(*args, **kwargs)

        res = await self.submit(request, *args, **kwargs)

        return await res

    async def revoke(self, request_id: uuid.UUID, *, force: bool = False) -> Result:
        """
        Revoke the execution of a request.

        If the request is already completed, this method returns
        the associated result as-is. Optionally, `force=True` may be set
        in order to ignore the state check.

        This will also revoke any request that's launched as a child of this one,
        recursively.

        Returns the cancelled result.
        """
        res = await self.result_backend.get_or_create(request_id)

        if not force and res.done:
            _log.warning(
                "Attempting to cancel result %r that's already done, this is a no-op",
                res.id,
            )
            return res

        _log.info("Revoking request id=%r", res)

        await res.revoke()

        payload = MessagePayload(
            id=str(uuid.uuid4()),
            kind=Revoke.MESSAGE_KIND,
            payload=Revoke(id=request_id).model_dump(),
        )

        await self.broker.send_control_message(payload)

        child_count = await res.children.count()
        if child_count:
            _log.info("Revoking %r children of id=%r", child_count, res.id)

            # Abort children.
            async for child_id in res.children.iter_ids():
                await self.revoke(child_id, force=force)

        return res

    async def connect(self):
        """Connect this app and its components to their respective backends."""
        if self._connected:
            return

        self.broker = self._create_broker()

        self.result_backend = self._create_result_backend()
        self.state_backend = self._create_state_backend()

        self._connected = True

        await self._setup_broker()

        _log.debug("Connecting to result backend %s", self.result_backend)

        await self.result_backend.connect()

        _log.debug("Connected to result backend %s", self.result_backend)

        _log.debug("Connecting to state backend %s", self.state_backend)

        await self.state_backend.connect()

        _log.debug("Connected to state backend %s", self.state_backend)

    async def __aenter__(self):
        await self.connect()

        return self

    async def __aexit__(self, *args, **kwargs):
        await self.close()

    @shield
    async def close(self):
        """Close this app and its components's backends."""

        _log.info("Closing app")

        await asyncio.shield(self._stop())

        if self._run_result and not self._run_result.done():
            self._run_result.set_result(None)

        _log.info("Closed app")

    async def _stop(self):
        await self._call_on_stopping_middleware()

        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()

            try:
                await self._heartbeat_task
            except BaseException:  # pylint: disable=broad-except
                pass

            self._heartbeat_task = None

        _log.debug("Closing queue listeners")

        if self._consume_control_task:
            self._consume_control_task.cancel()

            try:
                await self._consume_control_task
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # pylint: disable=broad-except
                _log.debug("Error shutting down control consumption task", exc_info=exc)

            self._consume_control_task = None

        # Disconnect from the broker, this should NACK
        # all pending messages too.
        _log.debug("Closing broker connection")
        if self.broker:
            await self.broker.close()

        # Stop the worker
        await self._stop_worker()

        # Remove service instances
        for svc in self.services:
            if isinstance(svc, ClassService):
                try:
                    svc.close()
                    await svc.wait_closed()
                except Exception as exc:  # pylint: disable=broad-except
                    _log.error("Error closing service %r", svc, exc_info=exc)

        self.services.clear()

        # Finally, shut down the state and result backends.
        _log.debug("Closing backends")
        if self.result_backend:
            try:
                await self.result_backend.close()
            except Exception as exc:  # pylint: disable=broad-except
                _log.error("Error closing result backend", exc_info=exc)

        if self.state_backend:
            try:
                await self.state_backend.close()
            except Exception as exc:  # pylint: disable=broad-except
                _log.error("Error closing state backend", exc_info=exc)

        self._connected = False

        await self._call_on_stopped_middleware()

    async def purge_task_queues(self) -> Dict[str, int]:
        """
        Purge all known task queues.

        Returns a dict where the keys are the names of the queues,
        and the values are the number of messages purged.
        """
        deleted_per_queue = {}

        for queue in self.get_task_queue_names():
            _log.info("Purging task queue=%r", queue)
            deleted_per_queue[queue] = await self.broker.purge_task_queue(queue)

        return deleted_per_queue

    async def purge_control_queue(self) -> int:
        """
        Purges the control queue related to this app.

        Returns the number of messages purged.
        """
        return await self.broker.purge_control_queue()

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        return self._loop

    def _create_broker(self) -> BaseBroker:
        return AmqpBroker(config=self.config.broker, app=self)

    def _create_result_backend(self) -> BaseResultBackend:
        return RedisResultBackend(self.config.result_backend, app=self)

    def _create_state_backend(self) -> BaseStateBackend:
        return RedisStateBackend(self.config.state_backend, app=self)

    def _load_modules(self):
        for module in self.config.imports:
            importlib.import_module(module)

    def _log_tasks_and_queues(self):

        all_tasks = self.task_registry.registered_task_names

        tasks_msg = "\n".join(
            f"\t - {t!r} (queue={self._get_task_route(t)!r})" for t in all_tasks
        )

        _log.info("Registered %r tasks:\n%s", len(all_tasks), tasks_msg)

        all_queues = self.get_task_queue_names()

        queues_msg = "\n".join(f"\t - {q!r}" for q in all_queues)

        _log.info("Registered %r queues:\n%s", len(all_queues), queues_msg)

    async def _setup_broker(self):
        _log.debug("Connecting to broker %s", self.broker)

        await self.broker.connect()

        _log.debug("Connected to broker %r", self.broker)

        _log.debug("Setting up task queues")

        for queue_name in self.get_task_queue_names():
            await self.broker.setup_task_queue(TaskQueue(name=queue_name))

        _log.debug("Setup queues")

    async def _stop_worker(self):
        if self.worker is None or not self._worker_task:
            _log.debug("No worker running")
            return

        try:
            _log.debug("Closing worker")
            await self.worker.close()

            if self._worker_task is not None:
                self._worker_task.cancel()
                await self._worker_task

            _log.debug("Worker closed")
        except asyncio.CancelledError:
            pass
        except Exception as worker_close_exc:  # pylint: disable=broad-except
            _log.error(
                "Worker raised an exception while closing", exc_info=worker_close_exc
            )
        finally:
            self.worker = None
            self._worker_task = None

    async def _background_heartbeat(self):
        """
        Background task that checks if the event loop was blocked
        for too long.

        A crude check, it asyncio.sleep()s and checks if the time difference
        before and after sleeping is significantly higher. This could bring problems,
        for example, with task brokers, that may need to send periodic keep-alive messages
        to the broker in order to prevent connection drops.

        Error messages are logged in case the event loop got blocked for too long.
        """

        while True:
            current_ts = self.loop.time()

            await asyncio.sleep(5)

            next_ts = self.loop.time()

            diff = next_ts - current_ts

            if diff > 10:
                _log.error(
                    "Event loop seemed blocked for %.2fs (>10s), this could bring issues. Consider using asyncio.run_in_executor to run CPU-bound work",
                    diff,
                )
            else:
                _log.debug("Event loop heartbeat: %.2fs", diff)

    async def _consume_control_queue(self):
        """
        Reads messages from the control queue and dispatches them.
        """

        await self.broker.setup_control_queue()

        _log.debug("Listening on the control queue")

        async for msg in self.broker.consume_control_queue():
            try:
                await self._process_control_message(msg)
            except asyncio.CancelledError:
                break
            except Exception as exc:  # pylint: disable=broad-except
                _log.error(
                    "Could not process control queue message %r", msg, exc_info=exc
                )

    async def _process_control_message(self, msg: IncomingMessagePayload):
        _log.debug("Received control message id=%r", msg.id)

        try:
            if msg.kind == Revoke.MESSAGE_KIND:
                abort = Revoke.model_validate(msg.payload)

                _log.debug("Received request to revoke request id=%r", abort.id)

                if self.worker is None:
                    _log.debug("No worker running. Discarding revoke message.")
                    return

                try:
                    # Cancel the task's execution and ACK it on the broker
                    # to prevent it from re-running.
                    await self.worker.cancel(
                        abort.id, message_action=MessageCancellationAction.ACK
                    )
                except Exception as exc:  # pylint: disable=broad-except
                    _log.error(
                        "Error while cancelling request id=%r", abort.id, exc_info=exc
                    )

                return

            if msg.kind == "Query":
                query = QueryRequestMessage.model_validate(msg.payload)

                if query.name == "Status":
                    # Get the status of this worker and reply to the incoming message

                    if self.worker is None:
                        _log.debug("No worker running for Status query")
                        running_request_ids = []
                    else:
                        running_request_ids = list(self.worker.running_tasks.keys())

                    reply = StatusResponseMessage(
                        node_id=self.config.node_id,
                        payload=StatusResponseMessage.Status(
                            running_request_ids=running_request_ids,
                        ),
                    )

                    payload = MessagePayload(
                        id=str(reply.id), kind=reply.kind, payload=reply.model_dump()
                    )

                    return await self.broker.send_reply(msg, payload)

                _log.warning("Unknown query name=%r, discarding", query.name)
                return

            _log.warning("Unknown message kind=%r, discarding", msg.kind)
        finally:
            await msg.ack()

    async def _on_submitting(self, req: "Request", context: Optional["Context"]):
        for mw_inst in self._middleware:
            try:
                await mw_inst.on_request_submitting(req, context=context)
            except Exception as mw_exc:  # pylint: disable=broad-except
                _log.error("Middleware failed", exc_info=mw_exc)

    def _get_task_route(self, req: Union[str, Request]):
        if isinstance(req, Request):
            if req.queue_name is not None:
                _log.debug(
                    "Request %r has a queue override to route to queue=%r",
                    req,
                    req.queue_name,
                )
                return req.queue_name

            req = req.name

        route = self.config.task_routes.get(req)

        if route is not None:
            _log.debug(
                "Request %r has a config-set route to queue=%r",
                req,
                route,
            )
            return route

        default_queue = self.config.default_task_route

        _log.debug(
            "Request %r has no route set, falling back to default queue=%r",
            req,
            default_queue,
        )

        return default_queue

    async def _call_on_starting_middleware(self):
        for mw in self._middleware:
            try:
                await mw.on_app_starting(self)
            except Exception as exc:  # pylint: disable=broad-except
                _log.debug(
                    "Middleware %r failed on 'on_app_starting'", mw, exc_info=exc
                )

    async def _call_on_started_middleware(self):
        for mw in self._middleware:
            try:
                await mw.on_app_started(self)
            except Exception as exc:  # pylint: disable=broad-except
                _log.debug("Middleware %r failed on 'on_app_started'", mw, exc_info=exc)

    async def _call_on_stopping_middleware(self):
        for mw in self._middleware:
            try:
                await mw.on_app_stopping(self)
            except Exception as exc:  # pylint: disable=broad-except
                _log.debug(
                    "Middleware %r failed on 'on_app_stopping'", mw, exc_info=exc
                )

    async def _call_on_stopped_middleware(self):
        for mw in self._middleware:
            try:
                await mw.on_app_stopped(self)
            except Exception as exc:  # pylint: disable=broad-except
                _log.debug("Middleware %r failed on 'on_app_stopped'", mw, exc_info=exc)
