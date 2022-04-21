from mognet.state.state_backend_config import (
    RedisStateBackendSettings,
    StateBackendConfig,
)
from mognet.broker.broker_config import AmqpBrokerSettings, BrokerConfig
from mognet.backend.backend_config import (
    RedisResultBackendSettings,
    ResultBackendConfig,
)
from mognet.app.app import App
from mognet.app.app_config import AppConfig


config = AppConfig(
    result_backend=ResultBackendConfig(
        redis=RedisResultBackendSettings(url="redis://redis")
    ),
    broker=BrokerConfig(amqp=AmqpBrokerSettings(url="amqp://rabbitmq")),
    state_backend=StateBackendConfig(
        redis=RedisStateBackendSettings(url="redis://redis")
    ),
    task_routes={},
    minimum_concurrency=1,
)

config.imports = ["test.test_tasks"]


app = App(name="test", config=config)
