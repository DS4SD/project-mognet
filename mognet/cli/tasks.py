import asyncio
import logging
from typing import Optional
from uuid import UUID

import tabulate
import treelib
import typer

from mognet.cli.cli_state import state
from mognet.cli.models import OutputFormat
from mognet.cli.run_in_loop import run_in_loop
from mognet.exceptions.result_exceptions import ResultValueLost
from mognet.model.result import _ExceptionInfo
from mognet.model.result_tree import ResultTree

_log = logging.getLogger(__name__)

group = typer.Typer()


@group.command("get")
@run_in_loop
async def get(
    task_id: UUID = typer.Argument(  # noqa: B008
        ...,
        metavar="id",
        help="Task ID to get",
    ),
    include_value: bool = typer.Option(  # noqa: B008
        False,
        metavar="include-value",
        help="If passed, the task's result (or exception) will be printed",
    ),
) -> None:
    """Get a task's details"""

    async with state["app_instance"] as app:
        res = await app.result_backend.get(task_id)

        if res is None:
            _log.warning("Request %r does not exist", task_id)
            raise typer.Exit(1)

        table_data = [
            ("ID", res.id),
            ("Name", res.name),
            ("Arguments", res.request_kwargs_repr),
            ("State", res.state),
            ("Number of starts", res.number_of_starts),
            ("Number of stops", res.number_of_stops),
            ("Unexpected retry count", res.unexpected_retry_count),
            ("Parent", res.parent_id),
            ("Created at", res.created),
            ("Started at", res.started),
            ("Time in queue", res.queue_time),
            ("Finished at", res.finished),
            ("Runtime duration", res.duration),
            ("Node ID", res.node_id),
            ("Metadata", await res.get_metadata()),
        ]

        if include_value:
            try:
                value = await res.value.get_raw_value()

                if isinstance(value, _ExceptionInfo):
                    table_data.append(("Error raised", value.traceback))
                else:
                    table_data.append(("Result value", repr(value)))

            except ResultValueLost:
                table_data.append(("Result value", "<Lost>"))

        print(tabulate.tabulate(table_data))


@group.command("revoke")
@run_in_loop
async def revoke(
    task_id: UUID = typer.Argument(  # noqa: B008
        ...,
        metavar="id",
        help="Task ID to revoke",
    ),
    force: bool = typer.Option(  # noqa: B008
        False,
        metavar="force",
        help="Attempt revoking anyway if the result is complete. Helps cleaning up cases where subtasks may have been spawned.",
    ),
) -> None:
    """Revoke a task"""

    async with state["app_instance"] as app:

        res = await app.result_backend.get(task_id)

        ret_code = 0

        if res is None:
            _log.warning("Request %r does not exist", task_id)
            ret_code = 1

        await app.revoke(task_id, force=force)

        raise typer.Exit(ret_code)


@group.command("tree")
@run_in_loop
async def tree(
    task_id: UUID = typer.Argument(  # noqa: B008
        ...,
        metavar="id",
        help="Task ID to get tree from",
    ),
    format: OutputFormat = typer.Option(  # noqa: B008
        OutputFormat.TEXT, metavar="format"
    ),  # noqa: B008
    json_indent: int = typer.Option(2, metavar="json-indent"),  # noqa: B008
    text_label_format: str = typer.Option(  # noqa: B008
        "{name}(id={id!r}, state={state!r})",
        metavar="text-label-format",
        help="Label format for text format",
    ),
    max_depth: int = typer.Option(3, metavar="max-depth"),  # noqa: B008
    max_width: int = typer.Option(16, metavar="max-width"),  # noqa: B008
    poll: Optional[int] = typer.Option(None, metavar="poll"),  # noqa: B008
) -> None:
    """Get the tree (descendants) of a task"""

    async with state["app_instance"] as app:
        while True:
            result = await app.result_backend.get(task_id)

            if result is None:
                raise RuntimeError(f"Result for request id={task_id!r} does not exist")

            _log.info("Building tree for result id=%r", result.id)

            tree = await result.tree(max_depth=max_depth, max_width=max_width)

            if poll:
                typer.clear()

            if format == "text":
                t = treelib.Tree()

                _build_tree(t, text_label_format, tree)

                t.show()

            if format == "json":
                print(tree.json(indent=json_indent, ensure_ascii=False))

            if not poll:
                break

            await asyncio.sleep(poll)


def _build_tree(
    t: treelib.Tree,
    text_label_format: str,
    n: ResultTree,
    parent: Optional[ResultTree] = None,
) -> None:
    t.create_node(
        tag=text_label_format.format(**n.dict()),
        identifier=n.result.id,
        parent=None if parent is None else parent.result.id,
    )

    for c in n.children:
        _build_tree(t, text_label_format, c, parent=n)
