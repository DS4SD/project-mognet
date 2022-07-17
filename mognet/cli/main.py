import importlib
import logging
import os
import sys

import typer

from mognet import App
from mognet.cli import nodes, queues, run, tasks
from mognet.cli.cli_state import state
from mognet.cli.models import LogLevel

main = typer.Typer(name="mognet")


class _AppNotFound(Exception):
    pass


def _get_app(app_pointer: str) -> "App":
    sys.path.append(os.getcwd())

    if ":" not in app_pointer:
        app_module_name = app_pointer
        app_var_name = "app"
    else:
        app_module_name, app_var_name = app_pointer.split(":", 2)

    app_module = importlib.import_module(app_module_name)

    app = getattr(app_module, app_var_name or "app", None)

    if not isinstance(app, App):
        raise _AppNotFound(
            f"Could not find an app on {app_module_name!r}. Expected to find an attribute named {app_var_name!r}\n"
            f"You can specify a different attribute after a ':'.\n"
            f"Example: my_app:mognet_app"
        )

    return app


@main.callback()
def callback(
    app: str = typer.Argument(..., help="App module to import"),  # noqa: B008
    log_level: LogLevel = typer.Option("INFO", metavar="log-level"),  # noqa: B008
    log_format: str = typer.Option(  # noqa: B008
        "%(asctime)s:%(name)s:%(levelname)s:%(message)s", metavar="log-format"
    ),
) -> None:
    """Mognet CLI"""

    logging.basicConfig(
        level=getattr(logging, log_level.value),
        format=log_format,
    )

    app_instance = _get_app(app)
    state["app_instance"] = app_instance


main.add_typer(run.group, name="run", invoke_without_command=True)
main.add_typer(tasks.group, name="tasks")
main.add_typer(queues.group, name="queues")
main.add_typer(nodes.group, name="nodes")


if __name__ == "__main__":
    main()
