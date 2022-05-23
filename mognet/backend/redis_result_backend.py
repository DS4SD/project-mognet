from __future__ import annotations

import asyncio
import functools
import gzip
import json
import logging
from asyncio import shield
from datetime import timedelta
from typing import Any, AnyStr, Dict, Iterable, List, Optional, Set
from uuid import UUID

from pydantic.tools import parse_raw_as
from redis.asyncio import Redis, from_url
from redis.exceptions import ConnectionError, TimeoutError

from mognet.backend.backend_config import Encoding, ResultBackendConfig
from mognet.backend.base_result_backend import AppParameters, BaseResultBackend
from mognet.exceptions.base_exceptions import NotConnected
from mognet.exceptions.result_exceptions import ResultValueLost
from mognet.model.result import Result, ResultValueHolder
from mognet.model.result_state import READY_STATES, ResultState
from mognet.tools.urls import censor_credentials

_log = logging.getLogger(__name__)


def _retry(func):
    @functools.wraps(func)
    async def retry_wrapper(self: RedisResultBackend, *args, **kwargs):
        last_err = None

        sleep_s = 1

        for attempt in range(self._retry_connect_attempts):
            try:
                return await func(self, *args, **kwargs)
            except (TimeoutError, ConnectionError) as redis_err:
                _log.error(
                    "Attempt %r/%r: Redis Error",
                    attempt + 1,
                    self._retry_connect_attempts,
                    exc_info=redis_err,
                )
                last_err = redis_err

            _log.error("Sleeping for %.2fs before next attempt", sleep_s)

            await asyncio.sleep(sleep_s)

            sleep_s = min(sleep_s * 2, self._retry_connect_timeout)

            if self._retry_lock.locked():
                continue

            async with self._retry_lock:
                await self._disconnect()
                await self._connect()

        if last_err is not None:
            raise last_err

    return retry_wrapper


class RedisResultBackend(BaseResultBackend):
    """
    Result backend that uses Redis for persistence.
    """

    def __init__(self, config: ResultBackendConfig, app: AppParameters) -> None:
        super().__init__(config, app)

        self._url = config.redis.url
        self.__redis = None
        self._connected = False

        # Holds references to tasks which are spawned by .wait()
        self._waiters: List[asyncio.Future] = []

        # Attributes for @_retry
        self._retry_connect_attempts = self.config.redis.retry_connect_attempts
        self._retry_connect_timeout = self.config.redis.retry_connect_timeout
        self._retry_lock = asyncio.Lock()

    @property
    def _redis(self) -> Redis:
        if self.__redis is None:
            raise NotConnected

        return self.__redis

    @_retry
    async def get(self, result_id: UUID) -> Optional[Result]:
        obj_key = self._format_key(result_id)

        async with self._redis.pipeline(transaction=True) as pip:
            # Since HGETALL returns an empty HASH for keys that don't exist,
            # test if it exists at all and use that to check if we should return null.
            pip.exists(obj_key)
            pip.hgetall(obj_key)

            exists, value, *_ = await shield(pip.execute())

        if not exists:
            return None

        return self._decode_result(value)

    @_retry
    async def get_or_create(self, result_id: UUID) -> Result:
        """
        Gets a result, or creates one if it doesn't exist.
        """
        async with self._redis.pipeline(transaction=True) as pip:

            result_key = self._format_key(result_id)

            pip.hsetnx(result_key, "id", json.dumps(str(result_id)).encode())
            pip.hgetall(result_key)

            if self.config.redis.result_ttl is not None:
                pip.expire(result_key, self.config.redis.result_ttl)

            # Also set the value, to a default holding an absence of result.
            value_key = self._format_key(result_id, "value")

            default_not_ready = ResultValueHolder.not_ready()
            encoded = self._encode_result_value(default_not_ready)

            if self.config.redis.result_value_ttl is not None:
                pip.expire(value_key, self.config.redis.result_value_ttl)

            for encoded_k, encoded_v in encoded.items():
                pip.hsetnx(value_key, encoded_k, encoded_v)

            existed, value, *_ = await shield(pip.execute())

        if not existed:
            _log.debug("Created result %r on key %r", result_id, result_key)

        return self._decode_result(value)

    def _encode_result_value(self, value: ResultValueHolder) -> Dict[str, bytes]:
        contents = value.json().encode()
        encoding = b"null"

        if self.config.redis.result_value_encoding == Encoding.GZIP:
            encoding = _json_bytes("gzip")
            contents = gzip.compress(contents)

        return {
            "contents": contents,
            "encoding": encoding,
            "content_type": _json_bytes("application/json"),
        }

    def _decode_result_value(self, encoded: Dict[bytes, bytes]) -> ResultValueHolder:
        if encoded.get(b"encoding") == _json_bytes("gzip"):
            contents = gzip.decompress(encoded[b"contents"])
        else:
            contents = encoded[b"contents"]

        if encoded.get(b"content_type") != _json_bytes("application/json"):
            raise ValueError(f"Unknown content_type={encoded.get(b'content_type')!r}")

        return ResultValueHolder.parse_raw(contents, content_type="application/json")

    @_retry
    async def set(self, result_id: UUID, result: Result):
        key = self._format_key(result_id)

        async with self._redis.pipeline(transaction=True) as pip:

            encoded = _encode_result(result)

            pip.hset(key, None, None, encoded)

            if self.config.redis.result_ttl is not None:
                pip.expire(key, self.config.redis.result_ttl)

            await shield(pip.execute())

    def _format_key(self, result_id: UUID, subkey: str = None) -> str:
        key = f"{self.app.name}.mognet.result.{str(result_id)}"

        if subkey:
            key = f"{key}/{subkey}"

        _log.debug(
            "Formatted result key=%r for id=%r and subkey=%r", key, subkey, result_id
        )

        return key

    @_retry
    async def add_children(self, result_id: UUID, *children: UUID):
        if not children:
            return

        # If there are children to add, add them to the set
        # on Redis using SADD
        children_key = self._format_key(result_id, "children")

        async with self._redis.pipeline(transaction=True) as pip:

            pip.sadd(children_key, *_encode_children(children))

            if self.config.redis.result_ttl is not None:
                pip.expire(children_key, self.config.redis.result_ttl)

            await shield(pip.execute())

    async def get_value(self, result_id: UUID) -> ResultValueHolder:
        value_key = self._format_key(result_id, "value")

        async with self._redis.pipeline(transaction=True) as pip:

            pip.exists(value_key)
            pip.hgetall(value_key)

            exists, contents = await shield(pip.execute())

            if not exists:
                raise ResultValueLost(result_id)

            return self._decode_result_value(contents)

    async def set_value(self, result_id: UUID, value: ResultValueHolder):
        value_key = self._format_key(result_id, "value")

        encoded = self._encode_result_value(value)

        async with self._redis.pipeline(transaction=True) as pip:

            pip.hset(value_key, None, None, encoded)

            if self.config.redis.result_value_ttl is not None:
                pip.expire(value_key, self.config.redis.result_value_ttl)

            await shield(pip.execute())

    async def delete(self, result_id: UUID, include_children: bool = True):
        if include_children:
            async for child_id in self.iterate_children_ids(result_id):
                await self.delete(child_id, include_children=True)

        key = self._format_key(result_id)
        children_key = self._format_key(result_id, "children")
        value_key = self._format_key(result_id, "value")
        metadata_key = self._format_key(result_id, "metadata")

        await shield(self._redis.delete(key, children_key, value_key, metadata_key))

    async def set_ttl(
        self, result_id: UUID, ttl: timedelta, include_children: bool = True
    ):
        if include_children:
            async for child_id in self.iterate_children_ids(result_id):
                await self.set_ttl(child_id, ttl, include_children=True)

        key = self._format_key(result_id)
        children_key = self._format_key(result_id, "children")
        value_key = self._format_key(result_id, "value")
        metadata_key = self._format_key(result_id, "metadata")

        await shield(self._redis.expire(key, ttl))
        await shield(self._redis.expire(children_key, ttl))
        await shield(self._redis.expire(value_key, ttl))
        await shield(self._redis.expire(metadata_key, ttl))

    async def connect(self):
        if self._connected:
            return

        self._connected = True

        await self._connect()

    async def close(self):
        self._connected = False

        await self._close_waiters()

        await self._disconnect()

    async def get_children_count(self, parent_result_id: UUID) -> int:
        children_key = self._format_key(parent_result_id, "children")

        return await shield(self._redis.scard(children_key))

    async def iterate_children_ids(
        self, parent_result_id: UUID, *, count: Optional[float] = None
    ):
        children_key = self._format_key(parent_result_id, "children")

        raw_child_id: bytes
        async for raw_child_id in self._redis.sscan_iter(children_key, count=count):
            child_id = UUID(bytes=raw_child_id)
            yield child_id

    async def iterate_children(
        self, parent_result_id: UUID, *, count: Optional[float] = None
    ):
        async for child_id in self.iterate_children_ids(parent_result_id, count=count):
            child = await self.get(child_id)

            if child is not None:
                yield child

    @_retry
    async def wait(
        self, result_id: UUID, timeout: Optional[float] = None, poll: float = 1
    ) -> Result:
        async def waiter():
            key = self._format_key(result_id=result_id)

            # Type def for the state key. It can (but shouldn't)
            # be null.
            t = Optional[ResultState]

            while True:
                raw_state = await shield(self._redis.hget(key, "state")) or b"null"

                state = parse_raw_as(t, raw_state)

                if state is None:
                    raise ResultValueLost(result_id)

                if state in READY_STATES:
                    final_result = await self.get(result_id)

                    if final_result is None:
                        raise RuntimeError(
                            f"Result id={result_id!r} that previously existed no longer does"
                        )

                    return final_result

                await asyncio.sleep(poll)

        waiter_task = asyncio.create_task(
            waiter(),
            name=f"RedisResultBackend:wait_for:{result_id}",
        )

        if timeout:
            waiter_task = asyncio.create_task(asyncio.wait_for(waiter_task, timeout))

        self._waiters.append(waiter_task)

        return await waiter_task

    async def get_metadata(self, result_id: UUID) -> Dict[str, Any]:
        key = self._format_key(result_id, "metadata")

        value = await shield(self._redis.hgetall(key))

        return _decode_json_dict(value)

    async def set_metadata(self, result_id: UUID, **kwargs: Any) -> None:
        key = self._format_key(result_id, "metadata")

        if not kwargs:
            return

        async with self._redis.pipeline(transaction=True) as pip:

            pip.hset(key, None, None, _dict_to_json_dict(kwargs))

            if self.config.redis.result_ttl is not None:
                pip.expire(key, self.config.redis.result_ttl)

            await shield(pip.execute())

    def __repr__(self):
        return f"RedisResultBackend(url={censor_credentials(self._url)!r})"

    async def __aenter__(self):
        await self.connect()

        return self

    async def __aexit__(self, *args, **kwargs):
        await self.close()

    async def _close_waiters(self):
        """
        Cancel any wait loop we have running.
        """
        while self._waiters:
            waiter_task = self._waiters.pop()

            try:
                _log.debug("Cancelling waiter %r", waiter_task)

                waiter_task.cancel()
                await waiter_task
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # pylint: disable=broad-except
                _log.debug("Error on waiter task %r", waiter_task, exc_info=exc)

    async def _create_redis(self):
        _log.debug("Creating Redis connection")
        redis: Redis = await from_url(
            self._url,
            max_connections=self.config.redis.max_connections,
        )

        return redis

    @_retry
    async def _connect(self):
        if self.__redis is None:
            self.__redis = await self._create_redis()

        await shield(self._redis.ping())

    async def _disconnect(self):
        redis = self.__redis

        if redis is not None:
            self.__redis = None
            _log.debug("Closing Redis connection")
            await redis.close()

    def _decode_result(self, json_dict: Dict[bytes, bytes]) -> Result:
        # Load the dict of JSON values first; then update it with overrides.
        value = _decode_json_dict(json_dict)
        return Result(self, **value)


def _encode_result(result: Result) -> Dict[str, bytes]:
    json_dict: dict = json.loads(result.json())
    return _dict_to_json_dict(json_dict)


def _dict_to_json_dict(value: Dict[str, Any]) -> Dict[str, bytes]:
    return {k: json.dumps(v).encode() for k, v in value.items()}


# Children are encoded as byte arrays to save 20B per item,
# this saves 20MB per 1,000,000 children.
def _encode_children(children: Iterable[UUID]) -> Set[bytes]:
    return {c.bytes for c in children}


def _decode_json_dict(json_dict: Dict[bytes, AnyStr]) -> dict:
    """
    Decode a dict coming from hgetall/hmget, which is encoded with bytes as keys
    and bytes or str as values, containing JSON values.
    """
    return {k.decode(): json.loads(v) for k, v in json_dict.items()}


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value).encode()
