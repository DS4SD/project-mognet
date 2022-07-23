from typing import Optional

from pydantic import BaseModel


class RedisStateBackendSettings(BaseModel):
    """Configuration for the Redis State Backend"""

    url: str = "redis://localhost:6379/"

    # How long each task's state should live for.
    state_ttl: int = 7200

    # Set the limit of connections on the Redis connection pool.
    # DANGER! Setting this to too low a value WILL cause issues opening connections!
    max_connections: Optional[int] = None


class StateBackendConfig(BaseModel):
    redis: RedisStateBackendSettings
