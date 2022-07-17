import typer

from mognet.cli.cli_state import state
from mognet.cli.run_in_loop import run_in_loop

group = typer.Typer()


@group.command("purge")
@run_in_loop
async def purge(
    force: bool = typer.Option(False),  # noqa: B008
) -> None:
    """Purge task and control queues"""

    if not force:
        typer.echo("Must pass --force")
        raise typer.Exit(1)

    async with state["app_instance"] as app:
        await app.connect()

        purged_task_counts = await app.purge_task_queues()
        purged_control_count = await app.purge_control_queue()

        typer.echo("Purged the following queues:")

        for queue_name, count in purged_task_counts.items():
            typer.echo(f"\t- {queue_name!r}: {count!r}")

        typer.echo(f"Purged {purged_control_count!r} control messages")
