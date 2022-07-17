from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    from mognet.app.app_config import AppConfig
    from mognet.context.context import Context

_TReturn = TypeVar("_TReturn")

_TSelf = TypeVar("_TSelf")


class ClassService(Generic[_TReturn], metaclass=ABCMeta):
    """
    Base class for object-based services retrieved
    through Context#get_service()

    To get instances of a class-based service using
    Context#get_service(), pass the class itself,
    and an instance of the class will be returned.

    Note that the instances are *singletons*.

    The instances, when created, get access to the app's configuration.
    """

    def __init__(self, config: "AppConfig") -> None:
        self.config = config

    @abstractmethod
    def __call__(self, context: "Context", *args: Any, **kwds: Any) -> _TReturn:
        raise NotImplementedError

    def __enter__(self: _TSelf) -> _TSelf:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def close(self) -> None:
        pass

    async def wait_closed(self) -> None:
        pass
