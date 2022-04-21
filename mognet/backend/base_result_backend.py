import asyncio
from abc import ABCMeta, abstractmethod
from datetime import timedelta
from typing import (
    Any,
    AsyncGenerator,
    Dict,
    List,
    Optional,
    Protocol,
    Union,
)
from uuid import UUID

from mognet.backend.backend_config import ResultBackendConfig
from mognet.model.result import Result, ResultValueHolder

ResultOrId = Union[UUID, "Result"]


class AppParameters(Protocol):
    name: str


class BaseResultBackend(metaclass=ABCMeta):
    """Base interface to implemenent a Result Backend."""

    config: ResultBackendConfig
    app: AppParameters

    def __init__(self, config: ResultBackendConfig, app: AppParameters) -> None:
        super().__init__()

        self.config = config
        self.app = app

    @abstractmethod
    async def get(self, result_id: UUID) -> Optional[Result]:
        """
        Get a Result by it's ID.
        If it doesn't exist, this method returns None.
        """
        raise NotImplementedError

    async def get_many(self, *result_ids: UUID) -> List[Result]:
        """
        Get a list of Results by specifying their IDs.
        Results that don't exist will be removed from this list.
        """
        all_results = await asyncio.gather(*[self.get(r_id) for r_id in result_ids])

        return [r for r in all_results if r if r is not None]

    async def get_or_create(self, result_id: UUID) -> Result:
        """
        Get a Result by it's ID.
        If it doesn't exist, this method creates one.

        The returned Result will either be the existing one,
        or the newly-created one.
        """
        res = await self.get(result_id)

        if res is None:
            res = Result(self, id=result_id)
            await self.set(result_id, res)

        return res

    @abstractmethod
    async def set(self, result_id: UUID, result: Result) -> None:
        """
        Save a Result.
        """
        raise NotImplementedError

    async def wait(
        self, result_id: UUID, timeout: Optional[float] = None, poll: float = 0.1
    ) -> Result:
        """
        Wait until a result is ready.

        Raises `asyncio.TimeoutError` if a timeout is set and exceeded.
        """

        async def waiter():
            while True:
                result = await self.get(result_id)

                if result is not None and result.done:
                    return result

                await asyncio.sleep(poll)

        if timeout:
            return await asyncio.wait_for(waiter(), timeout)

        return await waiter()

    @abstractmethod
    async def get_children_count(self, parent_result_id: UUID) -> int:
        """
        Return the number of children of a Result.

        Returns 0 if the Result doesn't exist.
        """
        raise NotImplementedError

    @abstractmethod
    def iterate_children_ids(
        self, parent_result_id: UUID, *, count: Optional[int] = None
    ) -> AsyncGenerator[UUID, None]:
        """
        Get an AsyncGenerator for the IDs for the children of a Result.

        The AsyncGenerator will be empty if the Result doesn't exist.
        """
        raise NotImplementedError

    def iterate_children(
        self, parent_result_id: UUID, *, count: Optional[int] = None
    ) -> AsyncGenerator[Result, None]:
        """
        Get an AsyncGenerator for the children of a Result.

        The AsyncGenerator will be empty if the Result doesn't exist.
        """
        raise NotImplementedError

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args, **kwargs):
        return None

    async def connect(self):
        """
        Explicit method to connect to the backend provided by
        this Result backend.
        """

    async def close(self):
        """
        Explicit method to close the backend provided by
        this Result backend.
        """

    @abstractmethod
    async def add_children(self, result_id: UUID, *children: UUID) -> None:
        """
        Add children to a parent Result.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_value(self, result_id: UUID) -> ResultValueHolder:
        """
        Get the value of a Result.

        If the value is lost, ResultValueLost is raised.
        """
        raise NotImplementedError

    @abstractmethod
    async def set_value(self, result_id: UUID, value: ResultValueHolder) -> None:
        """
        Set the value of a Result.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_metadata(self, result_id: UUID) -> Dict[str, Any]:
        """
        Get the metadata of a Result.

        Returns an empty Dict if the Result doesn't exist.
        """
        raise NotImplementedError

    @abstractmethod
    async def set_metadata(self, result_id: UUID, **kwargs: Any) -> None:
        """
        Set metadata on a Result.
        """
        raise NotImplementedError

    @abstractmethod
    async def delete(self, result_id: UUID, include_children: bool = True) -> None:
        """
        Delete a Result.
        """
        raise NotImplementedError

    @abstractmethod
    async def set_ttl(
        self, result_id: UUID, ttl: timedelta, include_children: bool = True
    ) -> None:
        """
        Set expiration on a Result.

        If include_children is True, children will have the same TTL set.
        """
        raise NotImplementedError
