import asyncio
from datetime import datetime
from typing import List, Optional

import tabulate
import typer
from mognet.cli.cli_state import state
from mognet.cli.models import OutputFormat
from mognet.cli.run_in_loop import run_in_loop
from mognet.model.result import Result
from mognet.primitives.queries import StatusResponseMessage
from mognet.tools.dates import now_utc
from pydantic import BaseModel, Field

group = typer.Typer()


@group.command("status")
@run_in_loop
async def status(
    format: OutputFormat = typer.Option(OutputFormat.TEXT, metavar="format"),
    text_label_format: str = typer.Option(
        "{name}(id={id!r}, state={state!r})",
        metavar="text-label-format",
        help="Label format for text format",
    ),
    json_indent: int = typer.Option(2, metavar="json-indent"),
    poll: Optional[int] = typer.Option(
        None,
        metavar="poll",
        help="Polling interval, in seconds (default=None)",
    ),
    timeout: int = typer.Option(
        30,
        help="Timeout for querying nodes",
    ),
):
    """Query each node for their status"""

    async with state["app_instance"] as app:
        while True:
            each_node_status: List[StatusResponseMessage] = []

            async def read_status():
                async for node_status in app.get_current_status_of_nodes():
                    each_node_status.append(node_status)

            try:
                await asyncio.wait_for(read_status(), timeout=timeout)
            except asyncio.TimeoutError:
                pass

            all_result_ids = set()

            for node_status in each_node_status:
                all_result_ids.update(node_status.payload.running_request_ids)

            all_results_by_id = {
                r.id: r
                for r in await app.result_backend.get_many(
                    *all_result_ids,
                )
                if r is not None
            }

            report = _CliStatusReport()

            for node_status in each_node_status:
                running_requests = [
                    all_results_by_id[r]
                    for r in node_status.payload.running_request_ids
                    if r in all_results_by_id
                ]
                running_requests.sort(key=lambda r: r.created or now_utc())

                report.node_status.append(
                    _CliStatusReport.NodeStatus(
                        node_id=node_status.node_id, running_requests=running_requests
                    )
                )

            if poll:
                typer.clear()

            if format == "text":
                table_headers = ("Node name", "Running requests")

                table_data = [
                    (
                        n.node_id,
                        "\n".join(
                            text_label_format.format(**r.dict())
                            for r in n.running_requests
                        )
                        or "(Empty)",
                    )
                    for n in report.node_status
                ]

                typer.echo(
                    f"{len(report.node_status)} nodes replied as of {datetime.now()}:"
                )

                typer.echo(tabulate.tabulate(table_data, headers=table_headers))

            elif format == "json":
                typer.echo(report.model_dump_json(indent=json_indent))

            if not poll:
                break

            await asyncio.sleep(poll)


class _CliStatusReport(BaseModel):
    class NodeStatus(BaseModel):
        node_id: str
        running_requests: List[Result]

    node_status: List[NodeStatus] = Field(default_factory=list)
