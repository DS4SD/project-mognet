import asyncio
import inspect
import logging
from functools import wraps
from typing import (
    Any,
    Awaitable,
    Callable,
    NamedTuple,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

_T = TypeVar("_T")

_log = logging.getLogger(__name__)


async def _noop(*args: Any, **kwargs: Any) -> None:
    pass


def retryableasyncmethod(
    types: Tuple[Type[BaseException], ...],
    *,
    max_attempts: Union[int, str],
    wait_timeout: Union[float, str],
    lock: Optional[Union[asyncio.Lock, str]] = None,
    on_retry: Optional[Union[Callable[[BaseException], Awaitable[Any]], str]] = None,
) -> Callable[[_T], _T]:
    """
    Decorator to wrap an async method and make it retryable.
    """

    def make_retryable(func: _T) -> _T:
        if inspect.isasyncgenfunction(func):
            raise TypeError("Async generator functions are not supported")

        f: Any = cast(Any, func)

        @wraps(f)
        async def async_retryable_decorator(
            self: Any, *args: Any, **kwargs: Any
        ) -> Any:
            last_exc = None

            retry: Callable[..., Any] = _noop
            if isinstance(on_retry, str):
                retry = getattr(self, on_retry)
            elif callable(on_retry):
                retry = on_retry

            attempts: int
            if isinstance(max_attempts, str):
                attempts = getattr(self, max_attempts)
            else:
                attempts = max_attempts

            timeout: float
            if isinstance(wait_timeout, str):
                timeout = getattr(self, wait_timeout)
            else:
                timeout = wait_timeout

            retry_lock = None
            if isinstance(lock, str):
                retry_lock = getattr(self, lock)
            elif lock is not None:
                retry_lock = lock

            # Use an exponential backoff, starting with 1s
            # and with a maximum of whatever was configured
            current_wait_timeout = min(1, timeout)

            for attempt in range(1, attempts + 1):
                try:
                    return await f(self, *args, **kwargs)
                except types as exc:
                    _log.error("Attempt %r/%r failed", attempt, attempts, exc_info=exc)
                    last_exc = exc

                _log.debug("Waiting %.2fs before next attempt", current_wait_timeout)

                await asyncio.sleep(current_wait_timeout)

                current_wait_timeout = min(current_wait_timeout * 2, timeout)

                if retry_lock is not None:
                    if retry_lock.locked():
                        _log.debug("Already retrying, possibly on another method")
                    else:
                        async with retry_lock:
                            _log.debug("Calling retry method")
                            await retry(last_exc)
                else:
                    await retry(last_exc)

            if last_exc is None:
                last_exc = Exception("All %r attempts failed" % attempts)

            raise last_exc

        return cast(_T, async_retryable_decorator)

    return make_retryable
