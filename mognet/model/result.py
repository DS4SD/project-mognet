import base64
from mognet.exceptions.result_exceptions import ResultFailed, ResultNotReady, Revoked
import pickle
import importlib
import traceback
import logging
from typing import (
    Any,
    AsyncGenerator,
    Dict,
    Optional,
    TYPE_CHECKING,
)
from .result_state import (
    ERROR_STATES,
    READY_STATES,
    ResultState,
    SUCCESS_STATES,
)

from datetime import datetime, timedelta
from pydantic import BaseModel, TypeAdapter
from pydantic.fields import PrivateAttr
from mognet.tools.dates import now_utc
from uuid import UUID

if TYPE_CHECKING:
    from mognet.backend.base_result_backend import BaseResultBackend
    from .result_tree import ResultTree

_log = logging.getLogger(__name__)


class ResultChildren:
    """The children of a Result."""

    def __init__(self, result: "Result", backend: "BaseResultBackend") -> None:
        self._result = result
        self._backend = backend

    async def count(self) -> int:
        """The number of children."""
        return await self._backend.get_children_count(self._result.id)

    def iter_ids(self, *, count: Optional[int] = None) -> AsyncGenerator[UUID, None]:
        """Iterate the IDs of the children, optionally limited to a set count."""
        return self._backend.iterate_children_ids(self._result.id, count=count)

    def iter_instances(
        self, *, count: Optional[int] = None
    ) -> AsyncGenerator["Result", None]:
        """Iterate the instances of the children, optionally limited to a set count."""
        return self._backend.iterate_children(self._result.id, count=count)

    async def add(self, *children_ids: UUID):
        """For internal use."""
        await self._backend.add_children(self._result.id, *children_ids)


class ResultValueHolder(BaseModel):
    """
    Holds information about the type of the Result's value, and the raw value itself.

    Use `deserialize()` to parse the value according to the type.
    """

    value_type: str
    raw_value: Any

    def deserialize(self) -> Any:
        if self.raw_value is None:
            return None

        if self.value_type is not None:
            cls = _get_attr(self.value_type)

            value = TypeAdapter(cls).validate_python(self.raw_value)
        else:
            value = self.raw_value

        return value

    @classmethod
    def not_ready(cls):
        """
        Creates a value holder which is not ready yet.
        """
        value = _ExceptionInfo.from_exception(ResultNotReady())
        return cls(value_type=_serialize_name(value), raw_value=value)


class ResultValue:
    """
    Represents information about the value of a Result.
    """

    def __init__(self, result: "Result", backend: "BaseResultBackend") -> None:
        self._result = result
        self._backend = backend

        self._value_holder: Optional[ResultValueHolder] = None

    async def get_value_holder(self) -> ResultValueHolder:
        if self._value_holder is None:
            self._value_holder = await self._backend.get_value(self._result.id)

        return self._value_holder

    async def get_raw_value(self) -> Any:
        """Get the value. In case this is an exception, it won't be raised."""
        holder = await self.get_value_holder()
        return holder.deserialize()

    async def set_raw_value(self, value: Any):
        if isinstance(value, BaseException):
            value = _ExceptionInfo.from_exception(value)

        holder = ResultValueHolder(raw_value=value, value_type=_serialize_name(value))
        await self._backend.set_value(self._result.id, holder)


class _ExceptionInfo(BaseModel):
    name: str
    message: str

    traceback: str

    raw_data: Optional[str] = None
    raw_data_encoding: Optional[str] = None

    @classmethod
    def from_exception(cls, exception: BaseException):
        try:
            raw_data = pickle.dumps(exception)
        except Exception as unencodable:  # pylint: disable=broad-except
            _log.debug(
                "Exception of type %r is not encodable",
                type(exception),
                exc_info=unencodable,
            )
            raw_data = pickle.dumps(Exception(str(exception)))

        return cls(
            name=_serialize_name(exception),
            message=str(exception),
            raw_data=base64.b64encode(raw_data).decode(),
            raw_data_encoding="application/python-pickle",
            traceback="\n".join(
                traceback.format_exception(
                    type(exception), exception, exception.__traceback__
                )
            ),
        )

    @property
    def exception(self) -> Exception:
        if (
            self.raw_data is not None
            and self.raw_data_encoding == "application/python-pickle"
        ):
            return pickle.loads(base64.b64decode(self.raw_data))

        return Exception(self.message)


class Result(BaseModel):
    """
    Represents the result of executing a [`Request`][mognet.Request].

    It contains, along the return value (or raised exception),
    information on the resulting state, how many times it started,
    and timing information.
    """

    id: UUID
    name: Optional[str] = None
    state: ResultState = ResultState.PENDING

    number_of_starts: int = 0
    number_of_stops: int = 0

    parent_id: Optional[UUID] = None

    created: Optional[datetime] = None
    started: Optional[datetime] = None
    finished: Optional[datetime] = None

    node_id: Optional[str] = None

    request_kwargs_repr: Optional[str] = None

    _backend: "BaseResultBackend" = PrivateAttr()
    _children: Optional[ResultChildren] = PrivateAttr()
    _value: Optional[ResultValue] = PrivateAttr()

    def __init__(self, backend: "BaseResultBackend", **data) -> None:
        super().__init__(**data)
        self._backend = backend
        self._children = None
        self._value = None

    @property
    def children(self) -> ResultChildren:
        """Get an iterator on the children of this Result. Non-recursive."""

        if self._children is None:
            self._children = ResultChildren(self, self._backend)

        return self._children

    @property
    def value(self) -> ResultValue:
        """Get information about the value of this Result"""
        if self._value is None:
            self._value = ResultValue(self, self._backend)

        return self._value

    @property
    def duration(self) -> Optional[timedelta]:
        """
        Returns the time it took to complete this result.

        Returns None if the result did not start or finish.
        """
        if not self.started or not self.finished:
            return None

        return self.finished - self.started

    @property
    def queue_time(self) -> Optional[timedelta]:
        """
        Returns the time it took to start the task associated to this result.

        Returns None if the task did not start.
        """
        if not self.created or not self.started:
            return None

        return self.started - self.created

    @property
    def done(self):
        """
        True if the result is in a terminal state (e.g., SUCCESS, FAILURE).
        See `READY_STATES`.
        """
        return self.state in READY_STATES

    @property
    def successful(self):
        """True if the result was successful."""
        return self.state in SUCCESS_STATES

    @property
    def failed(self):
        """True if the result failed or was revoked."""
        return self.state in ERROR_STATES

    @property
    def revoked(self):
        """True if the result was revoked."""
        return self.state == ResultState.REVOKED

    @property
    def unexpected_retry_count(self) -> int:
        """
        Return the number of times the task associated with this result was retried
        as a result of an unexpected error, such as a SIGKILL.
        """
        return max(0, self.number_of_starts - self.number_of_stops)

    async def wait(self, *, timeout: Optional[float] = None, poll: float = 0.1) -> None:
        """Wait for the task associated with this result to finish."""
        updated_result = await self._backend.wait(self.id, timeout=timeout, poll=poll)

        await self._refresh(updated_result)

    async def revoke(self) -> "Result":
        """
        Revoke this Result.

        This shouldn't be called directly, use the method on the App class instead,
        as that will also revoke the children, recursively.
        """
        self.state = ResultState.REVOKED
        self.number_of_stops += 1
        self.finished = now_utc()
        await self._backend.set(self.id, self)
        return self

    async def get(self) -> Any:
        """
        Gets the value of this `Result` instance.

        Raises `ResultNotReady` if it's not ready yet.
        Raises any stored exception if the result failed

        Returns the stored value otherwise.

        Use `value.get_raw_value()` if you want access to the raw value.
        Call `wait` to wait for the value to be available.

        Optionally, `await` the result instance.
        """

        if not self.done:
            raise ResultNotReady()

        value = await self.value.get_raw_value()

        if self.state == ResultState.REVOKED:
            raise Revoked(self)

        if self.failed:
            if value is None:
                value = ResultFailed(self)

            # Re-hydrate exceptions.
            if isinstance(value, _ExceptionInfo):
                raise value.exception

            if not isinstance(value, BaseException):
                value = Exception(value)

            raise value

        return value

    async def set_result(
        self,
        value: Any,
        state: ResultState = ResultState.SUCCESS,
    ) -> "Result":
        """
        Set this Result to a success state, and store the value
        which will be return when one `get()`s this Result's value.
        """
        await self.value.set_raw_value(value)

        self.finished = now_utc()

        self.state = state
        self.number_of_stops += 1

        await self._update()

        return self

    async def set_error(
        self,
        exc: BaseException,
        state: ResultState = ResultState.FAILURE,
    ) -> "Result":
        """
        Set this Result to an error state, and store the exception
        which will be raised if one attempts to `get()` this Result's
        value.
        """

        _log.debug("Setting result id=%r to %r", self.id, state)

        await self.value.set_raw_value(exc)

        self.finished = now_utc()

        self.state = state
        self.number_of_stops += 1

        await self._update()

        return self

    async def start(self, *, node_id: Optional[str] = None) -> "Result":
        """
        Sets this `Result` as RUNNING, and logs the event.
        """
        self.started = now_utc()
        self.node_id = node_id

        self.state = ResultState.RUNNING
        self.number_of_starts += 1

        await self._update()

        return self

    async def resume(self, *, node_id: Optional[str] = None) -> "Result":
        if node_id is not None:
            self.node_id = node_id

        self.state = ResultState.RUNNING
        self.number_of_starts += 1

        await self._update()

        return self

    async def suspend(self) -> "Result":
        """
        Sets this `Result` as SUSPENDED, and logs the event.
        """

        self.state = ResultState.SUSPENDED
        self.number_of_stops += 1

        await self._update()

        return self

    async def tree(self, max_depth: int = 3, max_width: int = 500) -> "ResultTree":
        """
        Gets the tree of this result.

        :param max_depth: The maximum depth of the tree that's to be generated.
            This filters out results whose recursion levels are greater than it.
        """
        from .result_tree import ResultTree

        async def get_tree(result: Result, depth=1):
            _log.debug(
                "Getting tree of result id=%r, depth=%r max_depth=%r",
                result.id,
                depth,
                max_depth,
            )

            node = ResultTree(result=result, children=[])

            if depth >= max_depth and (await result.children.count()):
                _log.warning(
                    "Result id=%r has %r or more levels of children, which is more than the limit of %r. Results will be truncated",
                    result.id,
                    depth,
                    max_depth,
                )
                return node

            children_count = await result.children.count()
            if children_count > max_width:
                _log.warning(
                    "Result id=%r has %r children, which is more than the limit of %r. Results will be truncated",
                    result.id,
                    children_count,
                    max_width,
                )

            async for child in result.children.iter_instances(count=max_width):
                node.children.append(await get_tree(child, depth=depth + 1))

            node.children.sort(key=lambda r: r.result.created or now_utc())

            return node

        return await get_tree(self, depth=1)

    async def get_metadata(self) -> Dict[str, Any]:
        """Get the metadata associated with this Result."""
        return await self._backend.get_metadata(self.id)

    async def set_metadata(self, **kwargs: Any) -> None:
        """Set metadata on this Result."""
        await self._backend.set_metadata(self.id, **kwargs)

    async def _refresh(self, updated_result: Optional["Result"] = None):
        updated_result = updated_result or await self._backend.get(self.id)

        if updated_result is None:
            raise RuntimeError("Result no longer present")

        for k, v in updated_result.__dict__.items():
            if k == "id":
                continue

            setattr(self, k, v)

    async def _update(self):
        await self._backend.set(self.id, self)

    def __repr__(self):
        v = f"Result[{self.name or 'unknown'}, id={self.id!r}, state={self.state!r}]"

        if self.request_kwargs_repr is not None:
            v += f"({self.request_kwargs_repr})"

        return v

    # Implemented for asyncio's `await` functionality.
    def __hash__(self) -> int:
        return hash(f"Result_{self.id}")

    def __await__(self):
        yield from self.wait().__await__()
        value = yield from self.get().__await__()
        return value

    async def delete(self, include_children: bool = True):
        """
        Delete this Result from the backend.

        By default, this will delete children too.
        """
        await self._backend.delete(self.id, include_children=include_children)

    async def set_ttl(self, ttl: timedelta, include_children: bool = True):
        """
        Set TTL on this Result.

        By default, this will set it on the children too.
        """
        await self._backend.set_ttl(self.id, ttl, include_children=include_children)


def _get_attr(obj_spec):
    module, cls_name = obj_spec.split(":")

    mod = importlib.import_module(module)
    cls = getattr(mod, cls_name)

    return cls


def _serialize_name(v):
    if isinstance(v, type):
        return f"{v.__module__}:{v.__name__}"

    return _serialize_name(type(v))
