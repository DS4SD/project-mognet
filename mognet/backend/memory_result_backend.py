from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, AsyncGenerator, Dict, List, Optional, Set, Tuple
from uuid import UUID

from mognet.backend.backend_config import ResultBackendConfig
from mognet.backend.base_result_backend import AppParameters, BaseResultBackend
from mognet.exceptions.result_exceptions import ResultValueLost

if TYPE_CHECKING:
    from mognet.model.result import Result, ResultValueHolder


class MemoryResultBackend(BaseResultBackend):
    """
    Result backend that "persists" results in memory. Useful for testing,
    but this is not recommended for production setups.
    """

    def __init__(self, config: ResultBackendConfig, app: AppParameters) -> None:
        super().__init__(config, app)

        self._results: Dict[UUID, Result[Any]] = {}
        self._result_tree: Dict[UUID, Set[UUID]] = {}
        self._values: Dict[UUID, ResultValueHolder] = {}
        self._metadata: Dict[UUID, Dict[str, Any]] = {}

    async def get(self, result_id: UUID) -> Optional[Result[Any]]:
        return self._results.get(result_id, None)

    async def set(self, result_id: UUID, result: Result[Any]) -> None:
        self._results[result_id] = result

    async def get_children_count(self, parent_result_id: UUID) -> int:
        return len(self._result_tree.get(parent_result_id, set()))

    async def iterate_children_ids(
        self, parent_result_id: UUID, *, count: Optional[int] = None
    ) -> AsyncGenerator[UUID, None]:
        children = self._result_tree[parent_result_id]

        for idx, child in enumerate(children):
            yield child

            if count is not None and idx > count:
                break

    async def iterate_children(
        self, parent_result_id: UUID, *, count: Optional[int] = None
    ) -> AsyncGenerator[Result[Any], None]:
        async for child_id in self.iterate_children_ids(parent_result_id, count=count):
            child = self._results.get(child_id, None)

            if child is not None:
                yield child

    async def add_children(self, result_id: UUID, *children: UUID) -> None:
        self._result_tree.setdefault(result_id, set()).update(children)

    async def get_value(self, result_id: UUID) -> ResultValueHolder:
        value = self._values.get(result_id, None)

        if value is None:
            raise ResultValueLost(result_id)

        return value

    async def set_value(self, result_id: UUID, value: ResultValueHolder) -> None:
        self._values[result_id] = value

    async def get_metadata(self, result_id: UUID) -> Dict[str, Any]:
        meta = self._metadata.get(result_id, {})
        return meta

    async def set_metadata(self, result_id: UUID, **kwargs: Any) -> None:
        self._metadata.setdefault(result_id, {}).update(kwargs)

    async def delete(self, result_id: UUID, include_children: bool = True) -> None:
        if include_children:
            for child_id in self._result_tree.get(result_id, set()):
                await self.delete(child_id, include_children=include_children)

        self._results.pop(result_id, None)
        self._metadata.pop(result_id, None)
        self._values.pop(result_id, None)

    async def set_ttl(
        self, result_id: UUID, ttl: timedelta, include_children: bool = True
    ) -> None:
        pass

    async def close(self) -> None:
        self._metadata = {}
        self._result_tree = {}
        self._results = {}
        self._values = {}

        return await super().close()
