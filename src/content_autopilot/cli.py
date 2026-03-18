import typer
from typing import Optional

app = typer.Typer(help="Content Autopilot CLI")


@app.command()
def run_pipeline(
    dry_run: bool = typer.Option(False, "--dry-run", help="Run in dry-run mode without side effects")
) -> None:
    """Run the content collection and processing pipeline."""
    typer.echo(f"Running pipeline (dry_run={dry_run})...")


@app.command()
def start_scheduler() -> None:
    """Start the background scheduler for periodic tasks."""
    typer.echo("Starting scheduler...")


@app.command()
def status() -> None:
    """Show the current status of the system."""
    typer.echo("System status: OK")


if __name__ == "__main__":
    app()
