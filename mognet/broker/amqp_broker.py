import asyncio
import json
import logging
from asyncio.locks import Lock
from datetime import timedelta
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncGenerator,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
)

import aio_pika
import aio_pika.exceptions
import aiormq.exceptions
from aio_pika.channel import Channel
from aio_pika.connection import Connection
from aio_pika.exchange import Exchange, ExchangeType
from aio_pika.message import IncomingMessage, Message
from aio_pika.queue import Queue
from aiormq.exceptions import AMQPChannelError, ChannelInvalidStateError
from mognet.broker.base_broker import (
    BaseBroker,
    IncomingMessagePayload,
    MessagePayload,
    TaskQueue,
)
from mognet.broker.broker_config import BrokerConfig
from mognet.exceptions.base_exceptions import NotConnected
from mognet.exceptions.broker_exceptions import QueueNotFound
from mognet.model.queue_stats import QueueStats
from mognet.primitives.queries import QueryResponseMessage
from mognet.tools.retries import retryableasyncmethod
from mognet.tools.urls import censor_credentials
from pydantic.fields import PrivateAttr

_log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from mognet.app.app import App


class _AmqpIncomingMessagePayload(IncomingMessagePayload):
    _broker: "AmqpBroker" = PrivateAttr()
    _incoming_message: "IncomingMessage" = PrivateAttr()
    _processed: bool = PrivateAttr()

    def __init__(
        self, broker: "AmqpBroker", incoming_message: "IncomingMessage", **data: Any
    ) -> None:
        super().__init__(**data, reply_to=incoming_message.reply_to)

        self._broker = broker
        self._incoming_message = incoming_message
        self._processed = False

    async def ack(self):
        if self._processed:
            return True

        _log.debug("ACK message %r", self.id)

        self._processed = True

        # ACK and NACK will fail after connection errors.
        # So, instead of raising the exceptions, return a bool indicating
        # success or failure.
        try:
            await self._incoming_message.ack()
            return True
        except Exception as exc:  # pylint: disable=broad-except
            _log.error("Could not ACK message %r", self.id, exc_info=exc)
            return False

    async def nack(self):
        if self._processed:
            return True

        _log.debug("NACK message %r", self.id)

        self._processed = True

        # ACK and NACK will fail after connection errors.
        # So, instead of raising the exceptions, return a bool indicating
        # success or failure.
        try:
            await self._incoming_message.nack()
            return True
        except Exception as exc:  # pylint: disable=broad-except
            _log.error("Could not NACK message %r", self.id, exc_info=exc)
            return False


_RETRYABLE_ERRORS = (
    ConnectionError,
    AMQPChannelError,
    ChannelInvalidStateError,
    # Sometimes may be raised with "'writer' is None"
    AttributeError,
)


class AmqpBroker(BaseBroker):

    _task_channel: Channel
    _control_channel: Channel

    _task_queues: Dict[str, Queue]

    _direct_exchange: Exchange
    _control_exchange: Exchange

    _retry = retryableasyncmethod(
        _RETRYABLE_ERRORS,
        max_attempts="_retry_connect_attempts",
        wait_timeout="_retry_connect_timeout",
    )

    def __init__(self, app: "App", config: BrokerConfig) -> None:
        super().__init__()

        self._connected = False
        self.__connection = None

        self.config = config

        self._task_queues = {}
        self._control_queue = None

        # Lock to prevent duplicate queue declaration
        self._lock = Lock()

        self.app = app

        # Attributes for @retryableasyncmethod
        self._retry_connect_attempts = self.config.amqp.retry_connect_attempts
        self._retry_connect_timeout = self.config.amqp.retry_connect_timeout

        # List of callbacks for when connection drops
        self._on_connection_failed_callbacks: List[
            Callable[[Optional[BaseException]], Awaitable]
        ] = []

    @property
    def _connection(self) -> Connection:
        if self.__connection is None:
            raise NotConnected

        return self.__connection

    async def ack(self, delivery_tag: str):
        await self._task_channel.channel.basic_ack(delivery_tag)

    async def nack(self, delivery_tag: str):
        await self._task_channel.channel.basic_nack(delivery_tag)

    @_retry
    async def set_task_prefetch(self, prefetch: int):
        await self._task_channel.set_qos(prefetch_count=prefetch, global_=True)

    @_retry
    async def send_task_message(self, queue: str, payload: MessagePayload):
        amqp_queue = self._task_queue_name(queue)

        msg = Message(
            body=payload.json().encode(),
            content_type="application/json",
            content_encoding="utf-8",
            priority=payload.priority,
            message_id=payload.id,
        )

        await self._direct_exchange.publish(msg, amqp_queue)

        _log.debug(
            "Message %r sent to queue=%r (amqp queue=%r)", payload.id, queue, amqp_queue
        )

    async def consume_tasks(
        self, queue: str
    ) -> AsyncGenerator[IncomingMessagePayload, None]:

        amqp_queue = await self._get_or_create_task_queue(TaskQueue(name=queue))

        async for message in self._consume(amqp_queue):
            yield message

    async def consume_control_queue(
        self,
    ) -> AsyncGenerator[IncomingMessagePayload, None]:

        amqp_queue = await self._get_or_create_control_queue()

        async for message in self._consume(amqp_queue):
            yield message

    @_retry
    async def send_control_message(self, payload: MessagePayload):
        msg = Message(
            body=payload.json().encode(),
            content_type="application/json",
            content_encoding="utf-8",
            message_id=payload.id,
            expiration=timedelta(seconds=300),
        )

        # No queue name set because this is a fanout exchange.
        await self._control_exchange.publish(msg, "")

    @_retry
    async def _send_query_message(self, payload: MessagePayload):
        callback_queue = await self._task_channel.declare_queue(
            name=self._callback_queue_name,
            durable=False,
            exclusive=False,
            auto_delete=True,
            arguments={
                "x-expires": 30000,
                "x-message-ttl": 30000,
            },
        )
        await callback_queue.bind(self._direct_exchange)

        msg = Message(
            body=payload.json().encode(),
            content_type="application/json",
            content_encoding="utf-8",
            message_id=payload.id,
            expiration=timedelta(seconds=300),
            reply_to=callback_queue.name,
        )

        await self._control_exchange.publish(msg, "")

        return callback_queue

    async def send_query_message(
        self, payload: MessagePayload
    ) -> AsyncGenerator[QueryResponseMessage, None]:

        # Create a callback queue for getting the replies,
        # then send the message to the control exchange (fanout).
        # When done, delete the callback queue.

        callback_queue = None
        try:
            callback_queue = await self._send_query_message(payload)

            async with callback_queue.iterator() as iterator:
                async for message in iterator:
                    async with message.process():
                        contents: dict = json.loads(message.body)
                        msg = _AmqpIncomingMessagePayload(
                            broker=self, incoming_message=message, **contents
                        )
                        yield QueryResponseMessage.model_validate(msg.payload)
        finally:
            if callback_queue is not None:
                await callback_queue.delete()

    async def setup_control_queue(self):
        await self._get_or_create_control_queue()

    async def setup_task_queue(self, queue: TaskQueue):
        await self._get_or_create_task_queue(queue)

    @_retry
    async def _create_connection(self):
        connection = await aio_pika.connect_robust(
            self.config.amqp.url,
            reconnect_interval=self.app.config.reconnect_interval,
            client_properties={
                "connection_name": self.app.config.node_id,
            },
        )

        # All callback for broadcasting unexpected connection drops
        connection.add_close_callback(self._send_connection_failed_events)

        return connection

    def add_connection_failed_callback(
        self, cb: Callable[[Optional[BaseException]], Awaitable]
    ):
        self._on_connection_failed_callbacks.append(cb)

    def _send_connection_failed_events(self, connection, exc=None):
        if not self._connected:
            _log.debug(
                "Not sending connection closed events because we are disconnected"
            )
            return

        _log.error("AMQP connection %r failed", connection, exc_info=exc)

        tasks = [cb(exc) for cb in self._on_connection_failed_callbacks]

        _log.info(
            "Notifying %r listeners of a disconnect",
            len(tasks),
        )

        def notify_task_completion_callback(fut: asyncio.Future):
            exc = fut.exception()

            if exc and not fut.cancelled():
                _log.error("Error notifying connection dropped", exc_info=exc)

        for task in tasks:
            notify_task = asyncio.create_task(task)
            notify_task.add_done_callback(notify_task_completion_callback)

    async def connect(self):
        if self._connected:
            return

        self._connected = True

        self.__connection = await self._create_connection()

        # Use two separate channels with separate prefetch counts.
        # This allows the task channel to increase the prefetch count
        # without affecting the control channel,
        # and allows the control channel to still receive messages, even if
        # the task channel has reached the full prefetch count.
        self._task_channel = await self._connection.channel()
        await self.set_task_prefetch(1)

        self._control_channel = await self._connection.channel()
        await self.set_control_prefetch(4)

        await self._create_exchanges()

        _log.debug("Connected")

    async def set_control_prefetch(self, prefetch: int):
        await self._control_channel.set_qos(prefetch_count=prefetch, global_=False)

    async def close(self):
        self._connected = False

        connection = self.__connection

        if connection is not None:
            self.__connection = None

            _log.debug("Closing connections")
            await connection.close()
            _log.debug("Connection closed")

    @_retry
    async def send_reply(self, message: IncomingMessagePayload, reply: MessagePayload):
        if not message.reply_to:
            raise ValueError("Message has no reply_to set")

        msg = Message(
            body=reply.json().encode(),
            content_type="application/json",
            content_encoding="utf-8",
            message_id=reply.id,
        )

        await self._direct_exchange.publish(msg, message.reply_to)

    async def purge_task_queue(self, queue: str) -> int:
        amqp_queue = self._task_queue_name(queue)

        if amqp_queue not in self._task_queues:
            _log.warning(
                "Queue %r (amqp=%r) does not exist in this broker", queue, amqp_queue
            )
            return 0

        result = await self._task_queues[amqp_queue].purge()

        deleted_count: int = result.message_count

        _log.info(
            "Deleted %r messages from queue=%r (amqp=%r)",
            deleted_count,
            queue,
            amqp_queue,
        )

        return deleted_count

    async def purge_control_queue(self) -> int:
        if not self._control_queue:
            _log.debug("Not listening on any control queue, not purging it")
            return 0

        result = await self._control_queue.purge()

        return result.message_count

    def __repr__(self):
        return f"AmqpBroker(url={censor_credentials(self.config.amqp.url)!r})"

    async def __aenter__(self):
        await self.connect()

        return self

    async def __aexit__(self, *args, **kwargs):
        await self.close()

        return None

    async def _create_exchanges(self):
        self._direct_exchange = await self._task_channel.declare_exchange(
            self._direct_exchange_name,
            type=ExchangeType.DIRECT,
            durable=True,
        )
        self._control_exchange = await self._control_channel.declare_exchange(
            self._control_exchange_name,
            type=ExchangeType.FANOUT,
        )

    async def _consume(
        self, amqp_queue: Queue
    ) -> AsyncGenerator[IncomingMessagePayload, None]:

        async with amqp_queue.iterator() as queue_iterator:
            msg: IncomingMessage
            async for msg in queue_iterator:

                try:
                    contents: dict = json.loads(msg.body)

                    payload = _AmqpIncomingMessagePayload(
                        broker=self, incoming_message=msg, **contents
                    )

                    _log.debug("Successfully parsed message %r", payload.id)

                    yield payload
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # pylint: disable=broad-except
                    _log.error(
                        "Error parsing contents of message %r, discarding",
                        msg.correlation_id,
                        exc_info=exc,
                    )

                    try:
                        await asyncio.shield(msg.ack())
                    except Exception as ack_err:
                        _log.error(
                            "Could not ACK message %r for discarding",
                            msg.correlation_id,
                            exc_info=ack_err,
                        )

    def _task_queue_name(self, name: str) -> str:
        return f"{self.app.name}.{name}"

    @property
    def _control_queue_name(self) -> str:
        return f"{self.app.name}.mognet.control.{self.app.config.node_id}"

    @property
    def _callback_queue_name(self) -> str:
        return f"{self.app.name}.mognet.callback.{self.app.config.node_id}"

    @property
    def _control_exchange_name(self) -> str:
        return f"{self.app.name}.mognet.control"

    @property
    def _direct_exchange_name(self) -> str:
        return f"{self.app.name}.mognet.direct"

    @_retry
    async def _get_or_create_control_queue(self) -> Queue:
        if self._control_queue is None:
            async with self._lock:
                if self._control_queue is None:
                    self._control_queue = await self._control_channel.declare_queue(
                        name=self._control_queue_name,
                        durable=False,
                        auto_delete=True,
                        arguments={
                            "x-expires": 30000,
                            "x-message-ttl": 30000,
                        },
                    )
                    await self._control_queue.bind(self._control_exchange)

                    _log.debug("Prepared control queue=%r", self._control_queue.name)

        return self._control_queue

    @_retry
    async def _get_or_create_task_queue(self, queue: TaskQueue) -> Queue:
        name = self._task_queue_name(queue.name)

        if name not in self._task_queues:
            async with self._lock:

                if name not in self._task_queues:
                    _log.debug("Preparing queue %r as AMQP queue=%r", queue, name)

                    self._task_queues[name] = await self._task_channel.declare_queue(
                        name,
                        durable=True,
                        arguments={"x-max-priority": queue.max_priority},
                    )

                    await self._task_queues[name].bind(self._direct_exchange)

                    _log.debug(
                        "Prepared task queue=%r as AMQP queue=%r", queue.name, name
                    )

        return self._task_queues[name]

    async def task_queue_stats(self, task_queue_name: str) -> QueueStats:
        """
        Get the stats of a task queue.
        """

        name = self._task_queue_name(task_queue_name)

        # AMQP can close the Channel on us if we try accessing an object
        # that doesn't exist. So, to avoid trouble when the same Channel
        # is being used to consume a queue, use an ephemeral channel
        # for this operation alone.
        async with self._connection.channel() as channel:
            try:
                queue = await channel.get_queue(name, ensure=False)

                declare_result = await queue.declare()
            except (
                aiormq.exceptions.ChannelNotFoundEntity,
                aio_pika.exceptions.ChannelClosed,
            ) as query_err:
                raise QueueNotFound(task_queue_name) from query_err

        return QueueStats(
            queue_name=task_queue_name,
            message_count=declare_result.message_count,
            consumer_count=declare_result.consumer_count,
        )
