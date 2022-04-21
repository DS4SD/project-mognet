import asyncio
import pytest
import time
from mognet import task, Context, App, Request
from mognet.model.result_state import ResultState
from test.test_tasks import add


@task(name="test.sync_slow_add")
def sync_slow_add(context: Context, n1: float, n2: float, delay: float) -> float:
    time.sleep(delay)
    return n1 + n2


@pytest.mark.asyncio
async def test_sync_slow_add(test_app: App):

    done = False
    max_delay = 0

    # To check that the event loop was not blocked,
    # have a background task that sleeps while the other is running.
    async def heartbeat():
        nonlocal max_delay

        while not done:
            start = time.monotonic()
            await asyncio.sleep(0.1)
            end = time.monotonic()

            max_delay = max(max_delay, end - start)

    task = asyncio.create_task(heartbeat())

    req = Request(name="test.sync_slow_add", kwargs=dict(n1=1, n2=2, delay=5))

    assert await test_app.run(req) == 3

    done = True

    await task

    assert max_delay < 1


@task(name="test.sync_context_call")
def sync_context_call(context: Context, message: str):
    # To check that a sync task can, albeit in an ugly way, still call to the
    # event loop to do things like getting it's own Result.

    res = context.call_threadsafe(context.get_result())
    context.call_threadsafe(res.set_metadata(message=message))


@pytest.mark.asyncio
async def test_sync_context_call(test_app: App):
    message = "Hello"

    req = Request(name="test.sync_context_call", kwargs=dict(message=message))

    await test_app.run(req)

    res = await test_app.result_backend.get(req.id)

    assert res is not None

    assert (await res.get_metadata())["message"] == message


@task(name="test.sync_add")
def sync_add(context: Context, n1: float, n2: float):
    return n1 + n2


@pytest.mark.asyncio
async def test_fails_with_invalid_if_bad_args_sync(test_app: App):
    req = Request(name="test.sync_add", args=(5, "not a number"))

    with pytest.raises(Exception):
        await test_app.run(req)

    res = await test_app.result_backend.get(req.id)

    assert res is not None
    assert res.state == ResultState.INVALID


@task(name="test.sync_call_subtask")
def sync_call_subtask(context: Context, n1: float, n2: float, delay: float) -> float:
    time.sleep(delay)

    result = context.call_threadsafe(context.run(add, n1, n2))

    assert isinstance(result, float)

    return result


@pytest.mark.asyncio
async def test_sync_call_subtask(test_app: App):

    req = test_app.create_request(sync_call_subtask, 1, 2, 0.5)

    assert await test_app.run(req) == 3
