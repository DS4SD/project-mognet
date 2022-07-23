import os

import pytest

from mognet import App, Context, Request, task
from mognet.exceptions.too_many_retries import TooManyRetries
from mognet.model.result_state import ResultState


@pytest.mark.asyncio
@pytest.mark.skip
async def test_fails_if_killed_too_many_times(test_app: App):
    req = Request(name="test.kill_self", args=(9, 4))

    with pytest.raises(TooManyRetries):
        await test_app.run(req)

    res = await test_app.result_backend.get(req.id)

    assert res is not None
    assert res.state == ResultState.FAILURE
    assert res.unexpected_retry_count >= test_app.config.max_retries


@task(name="test.kill_self")
async def kill_self(context: Context, signo: int, stop_after_starts: int):
    pid = os.getpid()

    current_result = await context.get_result()

    if current_result.number_of_starts >= stop_after_starts:
        return "stopping the killing spree"

    os.kill(pid, signo)


@pytest.mark.asyncio
@pytest.mark.skip
async def test_restarts_if_terminated(test_app: App):
    start_count = 2
    req = Request(name="test.kill_self", args=(15, start_count))

    await test_app.run(req)

    res = await test_app.result_backend.get(req.id)

    assert res is not None

    # no unexpected retries
    assert res.unexpected_retry_count == 0
