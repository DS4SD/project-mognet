import os
import socket
from typing import Any, Dict, List, Optional, Set

from mognet.backend.backend_config import ResultBackendConfig
from mognet.broker.broker_config import BrokerConfig
from mognet.state.state_backend_config import StateBackendConfig
from pydantic.fields import Field
from pydantic.main import BaseModel


def _default_node_id() -> str:
    return f"{os.getpid()}@{socket.gethostname()}"


class Queues(BaseModel):
    include: Set[str] = Field(default_factory=set)
    exclude: Set[str] = Field(default_factory=set)

    @property
    def is_valid(self):
        return not (len(self.include) > 0 and len(self.exclude) > 0)

    def ensure_valid(self):
        if not self.is_valid:
            raise ValueError(
                "Cannot specify both 'include' and 'exclude'. Choose either or none."
            )


class AppConfig(BaseModel):
    """
    Configuration for a Mognet application.
    """

    # An ID for the node. Defaults to a string containing
    # the current PID and the hostname.
    node_id: str = Field(default_factory=_default_node_id)

    # Configuration for the result backend.
    result_backend: ResultBackendConfig

    # Configuration for the state backend.
    state_backend: StateBackendConfig

    # Configuration for the task broker.
    broker: BrokerConfig

    # List of modules to import
    imports: List[str] = Field(default_factory=list)

    # Maximum number of tasks that this app can handle.
    max_tasks: Optional[int] = None

    # Maximum recursion depth for tasks that call other tasks.
    max_recursion: int = 64

    # Defines the number of times a task that unexpectedly
    # failed (i.e., SIGKILL) can be retried.
    max_retries: int = 3

    # Default task route to send messages to.
    default_task_route: str = "tasks"

    # A mapping of [task name] -> [queue] that overrides the queue on which a task is listening.
    # If a task is not here, it will default to the queue set in [default_task_route].
    task_routes: Dict[str, str] = Field(default_factory=dict)

    # Specify which queues to listen, or not listen, on.
    task_queues: Queues = Field(default_factory=Queues)

    # The minimum prefetch count. Task consumption will start with
    # this value, and is then incremented based on the number of waiting
    # tasks that are running.
    # A higher value allows more tasks to run concurrently on this node.
    minimum_concurrency: int = 1

    # The minimum prefetch count. This helps ensure that not too many
    # recursive tasks run on this node.
    # Bear in mind that, if set, you can run into deadlocks if you have
    # overly recursive tasks.
    maximum_concurrency: Optional[int] = None

    # Settings that can be passed to instances retrieved via
    # Context#get_service()
    services_settings: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_file(cls, file_path: str) -> "AppConfig":
        with open(file_path, "r", encoding="utf-8") as config_file:
            return cls.model_validate_json(config_file.read())

    # Maximum number of attempts to connect
    max_reconnect_retries: int = 5

    # Time to wait between reconnects
    reconnect_interval: float = 5
