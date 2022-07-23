from dataclasses import dataclass

import pytest
from pydantic.main import BaseModel

from mognet import App, Context, Request, task
from mognet.exceptions.task_exceptions import InvalidTaskArguments
from mognet.model.result_state import ResultState
from mognet.tasks.task_registry import UnknownTask


@pytest.mark.asyncio
async def test_fails_with_invalid_if_task_does_not_exist(test_app: App):
    req = Request(name="test.no_such_task")

    with pytest.raises(UnknownTask):
        await test_app.run(req)

    res = await test_app.result_backend.get(req.id)

    assert res is not None
    assert res.state == ResultState.INVALID


@pytest.mark.asyncio
async def test_fails_with_invalid_if_bad_args(test_app: App):
    req = Request(name="test.add", args=(5, "not a number"))

    with pytest.raises(InvalidTaskArguments):
        await test_app.run(req)

    res = await test_app.result_backend.get(req.id)

    assert res is not None
    assert res.state == ResultState.INVALID


class AddModel(BaseModel):
    n1: int
    n2: int


@task(name="test.add_with_model")
async def add_with_model(context: Context, model: AddModel):
    return model.n1 + model.n2


@pytest.mark.asyncio
async def test_validates_models(test_app: App):
    raw_model = AddModel(n1=1, n2=2)

    req = Request(name="test.add_with_model", args=(raw_model,))

    result = await test_app.run(req)

    assert result == 3


@dataclass
class Greeting:
    who: str


@task(name="test.greet")
async def greet(context: Context, greeting: Greeting):
    return f"Hello, {greeting.who}"


@pytest.mark.asyncio
async def test_validates_dataclasses(test_app: App):
    raw_model = Greeting(who="André")

    req = Request(name="test.greet", args=(raw_model,))

    result = await test_app.run(req)

    assert result == "Hello, André"
