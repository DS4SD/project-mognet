from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, TypeVar, Generic


if TYPE_CHECKING:
    from mognet.app.app_config import AppConfig
    from mognet.context.context import Context

_TReturn = TypeVar("_TReturn")


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
    def __call__(self, context: "Context", *args, **kwds) -> _TReturn:
        raise NotImplementedError

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        pass

    async def wait_closed(self):
        pass