import asyncio

import pytest
import pytest_asyncio

from mognet import App


def create_app_fixture(app: App):
    """Create a Pytest fixture for a Mognet application."""

    @pytest_asyncio.fixture
    async def app_fixture():
        async with app:
            start_task = asyncio.create_task(app.start())
            yield app
            await app.close()

            try:
                start_task.cancel()
                await start_task
            except BaseException:  # pylint: disable=broad-except
                pass

    return app_fixture
