import os
from pathlib import Path

from mognet.app.app import App
from mognet.app.app_config import AppConfig
from mognet.backend.backend_config import (
    RedisResultBackendSettings,
    ResultBackendConfig,
)
from mognet.broker.broker_config import AmqpBrokerSettings, BrokerConfig
from mognet.state.state_backend_config import (
    RedisStateBackendSettings,
    StateBackendConfig,
)


def get_config():
    config_file_path = Path(os.getenv("MOGNET_CONFIG_FILE", "config.json"))

    if config_file_path.is_file():
        return AppConfig.parse_file(config_file_path)

    return AppConfig(
        result_backend=ResultBackendConfig(
            redis=RedisResultBackendSettings(url="redis://localhost:6379/0")
        ),
        broker=BrokerConfig(amqp=AmqpBrokerSettings(url="amqp://localhost:5672")),
        state_backend=StateBackendConfig(
            redis=RedisStateBackendSettings(url="redis://localhost:6379/0")
        ),
        task_routes={},
        minimum_concurrency=1,
    )


app = App(name="test", config=get_config())
