from abc import ABCMeta, abstractmethod
from typing import AsyncGenerator, Awaitable, Callable, List, Optional

from pydantic.main import BaseModel

from mognet.model.queue_stats import QueueStats
from mognet.primitives.queries import QueryResponseMessage


class MessagePayload(BaseModel):
    id: str
    kind: str
    payload: dict

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
    async def send_task_message(self, queue: str, payload: MessagePayload):
        raise NotImplementedError

    @abstractmethod
    async def send_control_message(self, payload: MessagePayload):
        raise NotImplementedError

    @abstractmethod
    def consume_tasks(self, queue: str) -> AsyncGenerator[IncomingMessagePayload, None]:
        raise NotImplementedError

    @abstractmethod
    def consume_control_queue(self) -> AsyncGenerator[IncomingMessagePayload, None]:
        raise NotImplementedError

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args, **kwargs):
        return None

    async def connect(self):
        pass

    async def close(self):
        pass

    @abstractmethod
    async def setup_task_queue(self, queue: TaskQueue):
        raise NotImplementedError

    @abstractmethod
    async def setup_control_queue(self):
        raise NotImplementedError

    async def set_task_prefetch(self, prefetch: int):
        pass

    async def set_control_prefetch(self, prefetch: int):
        pass

    @abstractmethod
    def send_query_message(
        self, payload: MessagePayload
    ) -> AsyncGenerator[QueryResponseMessage, None]:
        raise NotImplementedError

    @abstractmethod
    async def send_reply(self, message: IncomingMessagePayload, reply: MessagePayload):
        raise NotImplementedError

    @abstractmethod
    async def purge_task_queue(self, queue: str) -> int:
        raise NotImplementedError

    @abstractmethod
    async def purge_control_queue(self) -> int:
        raise NotImplementedError

    def add_connection_failed_callback(
        self, cb: Callable[[Optional[BaseException]], Awaitable]
    ):
        pass

    @abstractmethod
    async def task_queue_stats(self, task_queue_name: str) -> QueueStats:
        raise NotImplementedError
