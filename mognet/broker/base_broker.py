from abc import ABCMeta, abstractmethod
from typing import Any, AsyncGenerator, Callable, Coroutine, Optional

from pydantic.main import BaseModel

from mognet.model.queue_stats import QueueStats
from mognet.primitives.queries import QueryResponseMessage


class MessagePayload(BaseModel):
    id: str
    kind: str
    payload: Any

    priority: int = 5


class IncomingMessagePayload(MessagePayload, metaclass=ABCMeta):

    reply_to: Optional[str] = None

    @abstractmethod
    async def ack(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def nack(self) -> bool:
        raise NotImplementedError


class TaskQueue(BaseModel):
    name: str
    max_priority: int = 10
    # exchange: str = "mognet.tasks"


class BaseBroker(metaclass=ABCMeta):
    @abstractmethod
    async def send_task_message(self, queue: str, payload: MessagePayload) -> None:
        raise NotImplementedError

    @abstractmethod
    async def send_control_message(self, payload: MessagePayload) -> None:
        raise NotImplementedError

    @abstractmethod
    def consume_tasks(self, queue: str) -> AsyncGenerator[IncomingMessagePayload, None]:
        raise NotImplementedError

    @abstractmethod
    def consume_control_queue(self) -> AsyncGenerator[IncomingMessagePayload, None]:
        raise NotImplementedError

    async def __aenter__(self):  # type: ignore
        return self

    async def __aexit__(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    @abstractmethod
    async def setup_task_queue(self, queue: TaskQueue) -> None:
        raise NotImplementedError

    @abstractmethod
    async def setup_control_queue(self) -> None:
        raise NotImplementedError

    async def set_task_prefetch(self, prefetch: int) -> None:
        pass

    async def set_control_prefetch(self, prefetch: int) -> None:
        pass

    @abstractmethod
    def send_query_message(
        self, payload: MessagePayload
    ) -> AsyncGenerator[QueryResponseMessage, None]:
        raise NotImplementedError

    @abstractmethod
    async def send_reply(
        self, message: IncomingMessagePayload, reply: MessagePayload
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def purge_task_queue(self, queue: str) -> int:
        raise NotImplementedError

    @abstractmethod
    async def purge_control_queue(self) -> int:
        raise NotImplementedError

    def add_connection_failed_callback(
        self, cb: Callable[[Optional[BaseException]], Coroutine[Any, Any, Any]]
    ) -> None:
        pass

    @abstractmethod
    async def task_queue_stats(self, task_queue_name: str) -> QueueStats:
        raise NotImplementedError
