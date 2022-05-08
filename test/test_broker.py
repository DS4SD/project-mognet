from typing import TYPE_CHECKING

import pytest

from mognet.exceptions.broker_exceptions import QueueNotFound

if TYPE_CHECKING:
    from mognet import App


@pytest.mark.asyncio
async def test_broker_stats(test_app: "App"):
    stats = await test_app.broker.task_queue_stats("tasks")


@pytest.mark.asyncio
async def test_broker_stats_fails_when_queue_not_found(test_app: "App"):

    with pytest.raises(QueueNotFound):
        await test_app.broker.task_queue_stats("not_found")

    # But subsequent calls should still work...
    stats = await test_app.broker.task_queue_stats("tasks")
