import pytest
from mognet.testing.pytest_integration import create_app_fixture

from .app_instance import config, app


test_app = create_app_fixture(app)


@pytest.fixture
def app_config():
    return config
