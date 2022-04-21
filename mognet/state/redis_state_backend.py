import logging
import json
from typing import Any, Optional, TYPE_CHECKING, TypeVar
import aioredis
from mognet.exceptions.base_exceptions import NotConnected
from mognet.state.state_backend_config import StateBackendConfig
from mognet.state.base_state_backend import BaseStateBackend
from mognet.tools.urls import censor_credentials

if TYPE_CHECKING:
    from mognet.app.app import App


_TValue = TypeVar("_TValue")

_log = logging.getLogger(__name__)


class RedisStateBackend(BaseStateBackend):
    def __init__(self, config: StateBackendConfig, app: "App") -> None:
        super().__init__()

        self.config = config
        self.__redis = None
        self.app = app

    @property
    def _redis(self) -> aioredis.Redis:
        if self.__redis is None:
            raise NotConnected

        return self.__redis

    async def get(
        self, request_id: str, key: str, default: _TValue = None
    ) -> Optional[_TValue]:
        state_key = self._format_key(request_id)

        async with self._redis.pipeline(transaction=True) as tr:

            tr.hexists(state_key, key)
            tr.hget(state_key, key)
            tr.expire(state_key, self.config.redis.state_ttl)

            exists, value, *_ = await tr.execute()

        if not exists:
            _log.debug(
                "State of id=%r key=%r did not exist; returning default",
                request_id,
                key,
            )
            return default

        return json.loads(value)

    async def set(self, request_id: str, key: str, value: Any):
        state_key = self._format_key(request_id)

        async with self._redis.pipeline(transaction=True) as tr:

            tr.hset(state_key, key, json.dumps(value).encode())
            tr.expire(state_key, self.config.redis.state_ttl)

            await tr.execute()

    async def pop(
        self, request_id: str, key: str, default: _TValue = None
    ) -> Optional[_TValue]:
        state_key = self._format_key(request_id)

        async with self._redis.pipeline(transaction=True) as tr:

            tr.hexists(state_key, key)
            tr.hget(state_key, key)
            tr.hdel(state_key, key)
            tr.expire(state_key, self.config.redis.state_ttl)

            exists, value, *_ = await tr.execute()

        if not exists:
            _log.debug(
                "State of id=%r key=%r did not exist; returning default",
                request_id,
                key,
            )
            return default

        return json.loads(value)

    async def clear(self, request_id: str):
        state_key = self._format_key(request_id)

        _log.debug("Clearing state of id=%r", state_key)

        return await self._redis.delete(state_key)

    def _format_key(self, result_id: str) -> str:
        key = f"{self.app.name}.mognet.state.{result_id}"

        _log.debug("Formatted state key=%r for id=%r", key, result_id)

        return key

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args, **kwargs):
        await self.close()

    async def connect(self):
        redis: aioredis.Redis = aioredis.from_url(
            self.config.redis.url,
            max_connections=self.config.redis.max_connections,
        )
        self.__redis = redis

    async def close(self):
        redis = self.__redis

        if redis is not None:
            self.__redis = None
            await redis.close()

    def __repr__(self):
        return f"RedisStateBackend(url={censor_credentials(self.config.redis.url)!r})"
