from typing import ClassVar
from uuid import UUID

from pydantic.main import BaseModel


class Revoke(BaseModel):
    MESSAGE_KIND: ClassVar[str] = "Revoke"
    id: UUID
