from abc import ABCMeta, abstractmethod
from typing import Any, Optional, TypeVar
from uuid import UUID

_TValue = TypeVar("_TValue")


class BaseStateBackend(metaclass=ABCMeta):
    @abstractmethod
    async def get(
        self, request_id: UUID, key: str, default: Optional[_TValue] = None
    ) -> Optional[_TValue]:
        raise NotImplementedError

    @abstractmethod
    async def set(self, request_id: UUID, key: str, value: Any) -> None:
        raise NotImplementedError

    @abstractmethod
    async def pop(
        self, request_id: UUID, key: str, default: Optional[_TValue] = None
    ) -> Optional[_TValue]:
        raise NotImplementedError

    @abstractmethod
    async def clear(self, request_id: UUID) -> None:
        raise NotImplementedError

    async def __aenter__(self):  # type: ignore
        return self

    async def __aexit__(self, *args: Any, **kwargs: Any) -> None:
        return None

    @abstractmethod
    async def connect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError
