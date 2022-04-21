from abc import ABCMeta, abstractmethod
from typing import Any, Optional, TypeVar
from uuid import UUID

_TValue = TypeVar("_TValue")


class BaseStateBackend(metaclass=ABCMeta):
    @abstractmethod
    async def get(
        self, request_id: UUID, key: str, default: _TValue = None
    ) -> Optional[_TValue]:
        raise NotImplementedError

    @abstractmethod
    async def set(self, request_id: UUID, key: str, value: Any):
        raise NotImplementedError

    @abstractmethod
    async def pop(
        self, request_id: UUID, key: str, default: _TValue = None
    ) -> Optional[_TValue]:
        raise NotImplementedError

    @abstractmethod
    async def clear(self, request_id: UUID):
        raise NotImplementedError

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args, **kwargs):
        return None

    @abstractmethod
    async def connect(self):
        raise NotImplementedError

    @abstractmethod
    async def close(self):
        raise NotImplementedError
