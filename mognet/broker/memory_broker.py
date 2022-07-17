import asyncio
from asyncio import Queue
from typing import Any, AsyncGenerator, Dict
from uuid import uuid4

from pydantic.fields import PrivateAttr

from mognet.broker.base_broker import (
    BaseBroker,
    IncomingMessagePayload,
    MessagePayload,
    TaskQueue,
)
from mognet.model.queue_stats import QueueStats
from mognet.primitives.queries import QueryResponseMessage


class _InMemoryIncomingMessagePayload(IncomingMessagePayload):

    _broker: "InMemoryBroker" = PrivateAttr()
    _queue: "Queue[MessagePayload]" = PrivateAttr()

    def __init__(
        self, broker: "InMemoryBroker", queue: "Queue[MessagePayload]", **data: Any
    ) -> None:
        super().__init__(**data)

        self._broker = broker
        self._queue = queue

    async def ack(self) -> bool:
        await self._broker.ack_task()
        return True

    async def nack(self) -> bool:
        await self._queue.put(self)
        return True


class InMemoryBroker(BaseBroker):
    def __init__(self) -> None:
        super().__init__()

        self._control_prefetch: int = 1

        self._unacked_task_count: int = 0
        self._task_prefetch: int = 1
        self._task_event = asyncio.Event()

        self._task_queues: Dict[str, "Queue[MessagePayload]"] = {}
        self._control_queue: "Queue[MessagePayload]" = Queue()

        self._callback_queues: Dict[str, "Queue[MessagePayload]"] = {}

    async def send_task_message(self, queue: str, payload: MessagePayload) -> None:
        await self._task_queues[queue].put(payload)

    async def send_control_message(self, payload: MessagePayload) -> None:
        await self._control_queue.put(payload)

    async def consume_tasks(
        self, queue: str
    ) -> AsyncGenerator[IncomingMessagePayload, None]:
        q = self._task_queues[queue]

        while True:
            await self._task_event.wait()

            msg = await q.get()

            self._unacked_task_count += 1
            self._update_task_event()

            yield _InMemoryIncomingMessagePayload(
                broker=self,
                queue=q,
                id=msg.id,
                kind=msg.kind,
                payload=msg.payload,
                reply_to=None,
            )

    async def consume_control_queue(
        self,
    ) -> AsyncGenerator[IncomingMessagePayload, None]:
        while True:
            msg = await self._control_queue.get()
            yield _InMemoryIncomingMessagePayload(
                broker=self,
                queue=self._control_queue,
                id=msg.id,
                kind=msg.kind,
                payload=msg.payload,
                reply_to=None,
            )

    async def setup_task_queue(self, queue: TaskQueue) -> None:
        self._task_queues[queue.name] = Queue()

    async def setup_control_queue(self) -> None:
        pass

    def _update_task_event(self) -> None:
        if self._unacked_task_count < self._task_prefetch:
            self._task_event.set()
        else:
            self._task_event.clear()

    async def ack_task(self) -> None:
        self._unacked_task_count = max(0, self._unacked_task_count - 1)
        self._update_task_event()

    async def set_task_prefetch(self, prefetch: int) -> None:
        self._task_prefetch = prefetch
        self._update_task_event()

    async def set_control_prefetch(self, prefetch: int) -> None:
        self._control_prefetch = prefetch

    async def send_query_message(
        self, payload: MessagePayload
    ) -> AsyncGenerator[QueryResponseMessage, None]:
        queue_id = str(uuid4())

        try:
            q = self._callback_queues.setdefault(queue_id, Queue())

            msg = _InMemoryIncomingMessagePayload(
                broker=self,
                queue=q,
                id=payload.id,
                kind=payload.kind,
                reply_to=queue_id,
                payload=payload.payload,
            )

            await self._control_queue.put(msg)

            while True:
                response = await q.get()
                yield QueryResponseMessage.parse_obj(response.payload)
        finally:
            self._callback_queues.pop(queue_id, None)

    async def send_reply(
        self, message: IncomingMessagePayload, reply: MessagePayload
    ) -> None:
        if not message.reply_to:
            raise ValueError("No one to send reply to")

        q = self._callback_queues.get(message.reply_to)

        if q is None:
            raise ValueError(f"Addressee {message.reply_to!r} is gone")

        await q.put(reply)

    async def purge_task_queue(self, queue: str) -> int:
        q = self._task_queues[queue]
        return _purge_queue(q)

    async def purge_control_queue(self) -> int:
        return _purge_queue(self._control_queue)

    async def task_queue_stats(self, task_queue_name: str) -> QueueStats:
        q = self._task_queues[task_queue_name]

        return QueueStats(
            queue_name=task_queue_name,
            message_count=q.qsize(),
            consumer_count=1,
        )


def _purge_queue(q: Queue[Any]) -> int:
    old_size = q.qsize()

    while not q.empty():
        q.get_nowait()

    return old_size
