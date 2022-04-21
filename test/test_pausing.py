import pytest
from typing import List
from mognet.primitives.request import Request
from mognet import App, Context, task
from mognet.exceptions.task_exceptions import Pause


@task(name="test.paused_sum")
async def paused_sum(context: Context, nums: List[float]):
    total = await context.state.get("total", 0)
    last_index = await context.state.get("last_index", 0)

    if last_index >= len(nums):
        return total

    total += nums[last_index]
    last_index += 1

    await context.state.set("total", total)
    await context.state.set("last_index", last_index)

    raise Pause()


@pytest.mark.asyncio
async def test_pausing(test_app: App):
    req = Request(name="test.paused_sum", args=([1, 2, 3],))

    result = await test_app.run(req)

    assert result == 6

    res = await test_app.result_backend.get(req.id)

    assert res is not None

    assert res.unexpected_retry_count == 0
    assert res.number_of_starts == 4
    assert res.number_of_stops == 4
