import asyncio

from mognet import Context
from mognet.decorators.task_decorator import task


@task(name="test.fails")
async def fails(context: "Context", message: str = "Oops."):
    raise Exception(message)


@task(name="test.add")
async def add(context: "Context", n1: float, n2: float):
    return n1 + n2


@task(name="test.sleep")
async def sleep(context: "Context", time: float):
    await asyncio.sleep(time)
