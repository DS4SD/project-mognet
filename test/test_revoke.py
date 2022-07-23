import asyncio
import uuid

import pytest

from mognet import App, Context, Request, task
from mognet.model.result import ResultFailed
from mognet.model.result_state import ResultState


@pytest.mark.asyncio
async def test_revoke(test_app: App):
    req = Request(name="test.sleep", args=(10,))

    await test_app.submit(req)

    await asyncio.sleep(2)

    await test_app.revoke(req.id)

    res = await test_app.result_backend.get(req.id)

    assert res is not None

    assert res.state == ResultState.REVOKED
    assert res.revoked

    with pytest.raises(ResultFailed):
        await res


@task(name="test.recurses_after_wait")
async def recurses_after_wait(context: Context, child_id: uuid.UUID):
    req = Request(name="test.add", id=child_id, args=(1, 2))

    try:
        await asyncio.sleep(5)
    finally:
        await context.submit(req)


@pytest.mark.asyncio
async def test_revokes_children_if_parent_revoked(test_app: App):
    child_id = uuid.uuid4()

    req = Request(name="test.recurses_after_wait", args=(child_id,))

    await test_app.submit(req)

    await asyncio.sleep(1)

    await test_app.revoke(req.id)

    await asyncio.sleep(1)

    child_res = await test_app.result_backend.get(child_id)

    assert child_res is not None

    assert child_res.state == ResultState.REVOKED
    assert child_res.revoked

    with pytest.raises(ResultFailed):
        await child_res
