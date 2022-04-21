from typing import Type
from uuid import uuid4
from dataclasses import dataclass
import pytest
import pytest_asyncio

from mognet import AppConfig
from mognet.backend.base_result_backend import BaseResultBackend
from mognet.backend.memory_result_backend import MemoryResultBackend
from mognet.backend.redis_result_backend import RedisResultBackend
from mognet.model.result_state import ResultState


@dataclass
class _DummyApp:
    name: str


@pytest_asyncio.fixture(params=(RedisResultBackend, MemoryResultBackend))
async def result_backend(app_config: AppConfig, request):
    backend = request.param(app_config.result_backend, _DummyApp(name="test"))

    async with backend:
        yield backend


@pytest.mark.asyncio
async def test_result_backend(result_backend: BaseResultBackend):
    """
    Test that the basic operations -- get, set, delete -- work
    """
    res_id = uuid4()

    res = await result_backend.get_or_create(res_id)

    await res.set_result("Hello, world")

    # Check that the results are properly set.
    assert res.done and res.state == ResultState.SUCCESS
    assert await res.value.get_raw_value() == "Hello, world"
    assert res.finished is not None

    res_2 = await result_backend.get(res_id)

    assert res_2 is not None

    assert await res_2 == "Hello, world"

    await res_2.delete()

    assert await result_backend.get(res_id) is None


@pytest.mark.asyncio
async def test_result_backend_raises_exceptions_on_failures(
    result_backend: BaseResultBackend,
):
    """
    Test that awaiting a failed Result raises the stored exception.
    """
    res_id = uuid4()

    res = await result_backend.get_or_create(res_id)

    await res.set_result(Exception("Test"), ResultState.FAILURE)

    res_2 = await result_backend.get(res_id)

    assert res_2 is not None

    assert res_2.state == ResultState.FAILURE

    with pytest.raises(Exception) as raised_exc:
        await res_2

    assert raised_exc.match("Test")

    await result_backend.delete(res_id)
