import pytest
from mognet_demo.config import DemoConfig
from mognet_demo.mognet_app import app

from mognet.testing.pytest_integration import create_app_fixture


@pytest.fixture
def config():
    return DemoConfig.instance()


# This creates a fixture that you can use on your pydantic tests.
# It is responsible for starting a Worker before the test starts,
# and shutting it down afterwards.
mognet_app = create_app_fixture(app)
