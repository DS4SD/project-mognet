from pydantic import BaseModel


class AmqpBrokerSettings(BaseModel):
    url: str = "amqp://localhost:5672/"

    retry_connect_attempts: int = 10
    retry_connect_timeout: float = 30


class BrokerConfig(BaseModel):
    amqp: AmqpBrokerSettings
