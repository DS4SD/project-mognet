from __future__ import annotations

import json
import logging
import sys
from typing import TYPE_CHECKING, Any, Optional, TypeVar, cast
from uuid import UUID

from redis.asyncio import from_url

from mognet.exceptions.base_exceptions import NotConnected
from mognet.state.base_state_backend import BaseStateBackend
from mognet.state.state_backend_config import StateBackendConfig
from mognet.tools.urls import censor_credentials

if sys.version_info < (3, 10):
    from typing_extensions import TypeAlias
else:
    from typing import TypeAlias


if TYPE_CHECKING:
    from redis.asyncio import Redis  # noqa: F401

    from mognet.app.app import App


_TValue = TypeVar("_TValue")
_Redis: TypeAlias = "Redis[Any]"

_log = logging.getLogger(__name__)


class RedisStateBackend(BaseStateBackend):
    def __init__(self, config: StateBackendConfig, app: "App") -> None:
        super().__init__()

        self.config = config
        self.__redis: Optional[_Redis] = None
        self.app = app

    @property
    def _redis(self) -> _Redis:
        if self.__redis is None:
            raise NotConnected

        return self.__redis

    async def get(
        self, request_id: UUID, key: str, default: Optional[_TValue] = None
    ) -> Optional[_TValue]:
        state_key = self._format_key(request_id)

        async with self._redis.pipeline(transaction=True) as tr:

            _ = tr.hexists(state_key, key)
            _ = tr.hget(state_key, key)
            _ = tr.expire(state_key, self.config.redis.state_ttl)

            exists, value, *_ = await tr.execute()

        if not exists:
            _log.debug(
                "State of id=%r key=%r did not exist; returning default",
                request_id,
                key,
            )
            return default

        return cast(_TValue, json.loads(value))

    async def set(self, request_id: UUID, key: str, value: Any) -> None:
        state_key = self._format_key(request_id)

        async with self._redis.pipeline(transaction=True) as tr:

            _ = tr.hset(state_key, key, json.dumps(value).encode())
            _ = tr.expire(state_key, self.config.redis.state_ttl)

            await tr.execute()

    async def pop(
        self, request_id: UUID, key: str, default: Optional[_TValue] = None
    ) -> Optional[_TValue]:
        state_key = self._format_key(request_id)

        async with self._redis.pipeline(transaction=True) as tr:

            _ = tr.hexists(state_key, key)
            _ = tr.hget(state_key, key)
            _ = tr.hdel(state_key, key)
            _ = tr.expire(state_key, self.config.redis.state_ttl)

            exists, value, *_ = await tr.execute()

        if not exists:
            _log.debug(
                "State of id=%r key=%r did not exist; returning default",
                request_id,
                key,
            )
            return default

        return cast(_TValue, json.loads(value))

    async def clear(self, request_id: UUID) -> None:
        state_key = self._format_key(request_id)

        _log.debug("Clearing state of id=%r", state_key)

        await self._redis.delete(state_key)

    def _format_key(self, result_id: UUID) -> str:
        key = f"{self.app.name}.mognet.state.{result_id}"

        _log.debug("Formatted state key=%r for id=%r", key, result_id)

        return key

    async def __aenter__(self) -> RedisStateBackend:
        await self.connect()
        return self

    async def __aexit__(self, *args: Any, **kwargs: Any) -> None:
        await self.close()

    async def connect(self) -> None:
        redis: _Redis = from_url(
            self.config.redis.url,
            max_connections=self.config.redis.max_connections,
        )
        self.__redis = redis

    async def close(self) -> None:
        redis = self.__redis

        if redis is not None:
            self.__redis = None
            await redis.close()

    def __repr__(self) -> str:
        return f"RedisStateBackend(url={censor_credentials(self.config.redis.url)!r})"
