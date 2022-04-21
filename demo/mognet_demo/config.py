"""
Some configuration of the app.

The defaults are configured to point to the instances created on the
Docker Compose file.
"""

from functools import lru_cache
from typing import Optional

from pydantic import BaseModel, BaseSettings

from mognet import AppConfig
from mognet.app.app_config import ResultBackendConfig, StateBackendConfig, BrokerConfig
from mognet.backend.backend_config import RedisResultBackendSettings
from mognet.state.state_backend_config import RedisStateBackendSettings
from mognet.broker.broker_config import AmqpBrokerSettings


class S3Config(BaseModel):
    endpoint_url: str = "http://localhost:9000"
    ssl: bool = False
    verify: bool = False

    region: Optional[str] = None

    aws_access_key_id: str = "ACCESS"
    aws_secret_access_key: str = "SuperS3cret"

    bucket_name: str = "mognet-demo"


class DemoConfig(BaseSettings):
    s3: S3Config = S3Config()

    mognet: AppConfig = AppConfig(
        result_backend=ResultBackendConfig(
            redis=RedisResultBackendSettings(url="redis://localhost:6379"),
        ),
        state_backend=StateBackendConfig(
            redis=RedisStateBackendSettings(url="redis://localhost:6379"),
        ),
        broker=BrokerConfig(
            amqp=AmqpBrokerSettings(url="amqp://localhost:5672"),
        ),
    )

    @classmethod
    @lru_cache
    def instance(cls):
        return cls()
