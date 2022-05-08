import logging
from typing import Any, Callable, Optional, TypeVar, cast

from mognet.tasks.task_registry import TaskRegistry, task_registry

_log = logging.getLogger(__name__)


_T = TypeVar("_T")


def task(*, name: Optional[str] = None):
    """
    Register a function as a task that can be run.

    The name argument is recommended, but not required. It is used as an identifier
    for which task to run when creating Request objects.

    If the name is not provided, the function's full name (module + name) is used instead.
    Bear in mind that this means that if you rename the module or the function, things may break
    during rolling upgrades.
    """

    def task_decorator(t: _T) -> _T:
        reg = task_registry.get(None)

        if reg is None:
            _log.debug("No global task registry set. Creating one")

            reg = TaskRegistry()
            reg.register_globally()

        reg.add_task_function(cast(Callable, t), name=name)

        return t

    return task_decorator
