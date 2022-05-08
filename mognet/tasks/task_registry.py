import logging
from contextvars import ContextVar
from typing import Any, Callable, Dict, List, Optional, Protocol

from mognet.context.context import Context

_log = logging.getLogger(__name__)

task_registry: ContextVar["TaskRegistry"] = ContextVar("task_registry")


class TaskProtocol(Protocol):
    def __call__(self, context: Context, *args: Any, **kwds: Any) -> Any:
        ...


class UnknownTask(KeyError):
    def __init__(self, task_name: str) -> None:
        super().__init__(task_name)
        self.task_name = task_name

    def __str__(self):
        return f"Unknown task: {self.task_name!r}; did you forget to register it, or import it's module in the app's configuration?"


class TaskRegistry:

    _names_to_tasks: Dict[str, TaskProtocol]
    _tasks_to_names: Dict[TaskProtocol, str]

    def __init__(self):
        self._names_to_tasks = {}
        self._tasks_to_names = {}

    def get_task_function(self, name: str) -> TaskProtocol:
        try:
            return self._names_to_tasks[name]
        except KeyError as ke:
            raise UnknownTask(name) from ke

    def get_task_name(self, func: TaskProtocol) -> str:
        return self._tasks_to_names[func]

    @property
    def registered_task_names(self) -> List[str]:
        return list(self._names_to_tasks)

    def add_task_function(self, func: Callable, *, name: Optional[str] = None):
        full_func_name = _get_full_func_name(func)

        if name is None:
            name = full_func_name

        if name in self._names_to_tasks and func is not self._names_to_tasks[name]:
            raise RuntimeError(
                f"Task {name!r} is already registered to {self._names_to_tasks[name]}"
            )

        self._names_to_tasks[name] = func
        self._tasks_to_names[func] = name

        _log.debug("Registered function %r as task %r", full_func_name, name)

    def register_globally(self):
        task_registry.set(self)


def _get_full_func_name(func) -> str:
    func_name = getattr(func, "__qualname__", None) or getattr(func, "__name__", None)

    full_func_name = ".".join(
        n for n in [getattr(func, "__module__", None), func_name] if n
    )

    return full_func_name
