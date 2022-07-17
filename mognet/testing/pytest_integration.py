import asyncio
from typing import Any, AsyncIterable

import pytest_asyncio

from mognet import App


def create_app_fixture(app: App) -> Any:
    """Create a Pytest fixture for a Mognet application."""

    async def app_fixture() -> AsyncIterable[App]:
        async with app:
            start_task = asyncio.create_task(app.start())
            yield app
            await app.close()

            try:
                start_task.cancel()
                await start_task
            except BaseException:  # pylint: disable=broad-except
                pass

    return pytest_asyncio.fixture(app_fixture)
