from pydantic import BaseModel


class QueueStats(BaseModel):
    queue_name: str

    message_count: int
    consumer_count: int
