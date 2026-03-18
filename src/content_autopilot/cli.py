import typer
import asyncio

from content_autopilot.orchestrator.pipeline import Pipeline
from content_autopilot.orchestrator.scheduler import PipelineScheduler

app = typer.Typer(help="Content Autopilot CLI")


@app.command()
def run_pipeline(
    dry_run: bool = typer.Option(False, "--dry-run", help="Run in dry-run mode without side effects")
) -> None:
    pipeline = Pipeline(dry_run=dry_run)
    result = asyncio.run(pipeline.run())

    typer.echo(f"Status: {result.status}")
    typer.echo(
        "Collected: "
        f"{result.collected} -> Deduped: {result.deduped} -> "
        f"Scored: {result.scored} -> Published: {result.published}"
    )

    if result.errors:
        typer.echo(f"Errors: {len(result.errors)}")
        for error in result.errors[:5]:
            typer.echo(f"  - {error}")


@app.command()
def start_scheduler() -> None:
    scheduler = PipelineScheduler()
    scheduler.start()
    typer.echo("Scheduler started. Press Ctrl+C to stop.")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_forever()
    except (KeyboardInterrupt, SystemExit):
        scheduler.stop()
    finally:
        loop.close()


@app.command()
def status() -> None:
    typer.echo("Pipeline status: TODO - requires DB integration")


if __name__ == "__main__":
    app()
