"""
Backport of https://github.com/RedRoserade/aioitertools/blob/f86552753e626cb71a3a305b9ec890f97d771e6b/aioitertools/asyncio.py#L93

Should be upstreamed here: https://github.com/omnilib/aioitertools/pull/103
"""

import asyncio
from contextlib import suppress
from typing import Any, AsyncGenerator, AsyncIterable, Dict, Iterable, TypeVar

T = TypeVar("T")


async def as_generated(
    iterables: Iterable[AsyncIterable[T]],
    *,
    return_exceptions: bool = False,
) -> AsyncIterable[T]:
    """
    Yield results from one or more async iterables, in the order they are produced.
    Like :func:`as_completed`, but for async iterators or generators instead of futures.
    Creates a separate task to drain each iterable, and a single queue for results.
    If ``return_exceptions`` is ``False``, then any exception will be raised, and
    pending iterables and tasks will be cancelled, and async generators will be closed.
    If ``return_exceptions`` is ``True``, any exceptions will be yielded as results,
    and execution will continue until all iterables have been fully consumed.
    Example::
        async def generator(x):
            for i in range(x):
                yield i
        gen1 = generator(10)
        gen2 = generator(12)
        async for value in as_generated([gen1, gen2]):
            ...  # intermixed values yielded from gen1 and gen2
    """

    queue: asyncio.Queue[Dict[Any, Any]] = asyncio.Queue()

    tailer_count: int = 0

    async def tailer(iterable: AsyncIterable[T]) -> None:
        nonlocal tailer_count

        try:
            async for item in iterable:
                await queue.put({"value": item})
        except asyncio.CancelledError:
            if isinstance(iterable, AsyncGenerator):  # pragma:nocover
                with suppress(Exception):
                    await iterable.aclose()
            raise
        except Exception as exc:  # pylint: disable=broad-except
            await queue.put({"exception": exc})
        finally:
            tailer_count -= 1

            if tailer_count == 0:
                await queue.put({"done": True})

    tasks = [asyncio.ensure_future(tailer(iter)) for iter in iterables]

    if not tasks:
        # Nothing to do
        return

    tailer_count = len(tasks)

    try:
        while True:
            i = await queue.get()

            if "value" in i:
                yield i["value"]
            elif "exception" in i:
                if return_exceptions:
                    yield i["exception"]
                else:
                    raise i["exception"]
            elif "done" in i:
                break
    except (asyncio.CancelledError, GeneratorExit):
        pass
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()

        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
