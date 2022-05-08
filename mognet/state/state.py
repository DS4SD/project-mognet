from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from mognet import App


class State:
    """
    Represents state that can persist across task restarts.

    Has facilities for getting, setting, and removing values.

    The task's state is deleted when the task finishes.
    """

    request_id: UUID

    def __init__(self, app: "App", request_id: UUID) -> None:
        self._app = app
        self.request_id = request_id

    @property
    def _backend(self):
        return self._app.state_backend

    async def get(self, key: str, default: Any = None) -> Any:
        """Get a value."""
        return await self._backend.get(self.request_id, key, default)

    async def set(self, key: str, value: Any):
        """Set a value."""
        return await self._backend.set(self.request_id, key, value)

    async def pop(self, key: str, default: Any = None) -> Any:
        """Delete a value from the state and return it's value."""
        return await self._backend.pop(self.request_id, key, default)

    async def clear(self):
        """Clear all values."""
        return await self._backend.clear(self.request_id)
