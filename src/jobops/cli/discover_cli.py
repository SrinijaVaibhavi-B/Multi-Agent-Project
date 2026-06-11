"""CLI for the discovery agent."""

import click
from jobops.agents.discovery.runner import run_discovery


@click.group()
def discover():
    """Job discovery commands."""
    pass


@discover.command("run")
@click.option("--dry-run", is_flag=True, default=False, help="Fetch and filter but do not write to DB.")
@click.option("--time-frame", default="24h", show_default=True, help="Time window for job listings.")
@click.option("--location", default="United States", show_default=True, help="Location filter.")
def discover_run(dry_run: bool, time_frame: str, location: str):
    """Discover new jobs and ingest them into the pipeline."""
    results = run_discovery(dry_run=dry_run, time_frame=time_frame, location=location)

    click.echo("")
    click.echo("=" * 50)
    click.echo("  Discovery Summary")
    click.echo("=" * 50)
    click.echo(f"  Total fetched     : {results['total_fetched']}")
    click.echo(f"  Passed filters    : {results['total_passed']}")
    click.echo(f"  Filtered out      : {results['total_filtered']}")
    click.echo(f"  Duplicates skipped: {results['duplicates_skipped']}")
    if results["dry_run"]:
        click.echo(f"  Would insert      : {results['inserted']}  (dry run)")
    else:
        click.echo(f"  Inserted          : {results['inserted']}")
    click.echo("=" * 50)
