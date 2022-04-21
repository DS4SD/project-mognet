from datetime import timedelta, datetime, timezone
from mognet.exceptions.result_exceptions import Revoked
from mognet.model.result_state import ResultState
import time
import pytest

from typing import TYPE_CHECKING

from mognet import Request


if TYPE_CHECKING:
    from mognet import App


@pytest.mark.asyncio
async def test_sleep(test_app: "App"):
    req = Request(name="test.sleep", args=(5,))

    start = time.monotonic()

    await test_app.run(req)

    end = time.monotonic()

    assert 4 <= end - start <= 6


@pytest.mark.asyncio
async def test_sleep_with_timeout_fails_task(test_app: "App"):
    req = Request(name="test.sleep", args=(10,), deadline=timedelta(seconds=5))

    start = time.monotonic()

    with pytest.raises(Revoked):
        await test_app.run(req)

    end = time.monotonic()

    assert 4 <= end - start <= 6

    res = await test_app.result_backend.get(req.id)

    assert res is not None

    assert res.state == ResultState.REVOKED


@pytest.mark.asyncio
async def test_datetime_deadlines(test_app: "App"):
    req = Request(
        name="test.sleep",
        args=(10,),
        deadline=datetime.now(tz=timezone.utc) + timedelta(seconds=5),
    )

    start = time.monotonic()

    with pytest.raises(Revoked):
        await test_app.run(req)

    end = time.monotonic()

    assert 4 <= end - start <= 6

    res = await test_app.result_backend.get(req.id)

    assert res is not None

    assert res.state == ResultState.REVOKED


@pytest.mark.asyncio
async def test_past_deadline_fails_task(test_app: "App"):
    req = Request(
        name="test.sleep",
        args=(5,),
        deadline=datetime.now(tz=timezone.utc) - timedelta(seconds=10),
    )

    with pytest.raises(Revoked):
        await test_app.run(req)

    res = await test_app.result_backend.get(req.id)

    assert res is not None

    assert res.state == ResultState.REVOKED
