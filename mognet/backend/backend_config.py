from datetime import timedelta
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class Encoding(str, Enum):
    GZIP = "gzip"


class RedisResultBackendSettings(BaseModel):
    """Configuration for the Redis Result Backend"""

    url: str = "redis://localhost:6379/"

    # TTL for the results.
    result_ttl: Optional[int] = int(timedelta(days=21).total_seconds())

    # TTL for the result values. This is set lower than `result_ttl` to keep
    # the results themselves available for longer.
    result_value_ttl: Optional[int] = int(timedelta(days=7).total_seconds())

    # Encoding for the result values.
    result_value_encoding: Optional[Encoding] = Encoding.GZIP

    retry_connect_attempts: int = 10
    retry_connect_timeout: float = 30

    # Set the limit of connections on the Redis connection pool.
    # DANGER! Setting this to too low a value WILL cause issues opening connections!
    max_connections: Optional[int] = None


class ResultBackendConfig(BaseModel):
    redis: RedisResultBackendSettings
