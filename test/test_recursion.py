import pytest

from mognet import App, Context, Request, task


@task(name="test.recursive_factorial")
async def recursive_factorial(context: Context, n: int) -> int:
    if n == 0 or n == 1:
        return 1

    lower_rec = context.create_request(recursive_factorial, n - 1)

    return n * (await context.run(lower_rec))


@pytest.mark.asyncio
async def test_recursive_tasks(test_app: App):
    req = Request(name="test.recursive_factorial", args=(5,))

    result = await test_app.run(req)

    assert result == 120


@pytest.mark.asyncio
async def test_raises_recursion_error_if_too_much_recursion(test_app: App):
    req = Request(name="test.recursive_factorial", args=(100,))

    with pytest.raises(RecursionError):
        await test_app.run(req)
