"""CLI for the resume tailor agent."""

import click
from jobops.agents.tailor.runner import run_tailor


@click.group()
def tailor():
    """Resume tailoring commands."""
    pass


@tailor.command("run")
@click.option("--batch-size", default=10, show_default=True, help="Number of jobs to tailor.")
@click.option("--min-score", default=60, show_default=True, help="Minimum fit score to tailor for.")
@click.option("--dry-run", is_flag=True, default=False, help="Tailor but skip PDF render and upload.")
def tailor_run(batch_size, min_score, dry_run):
    """Tailor resumes for top queued jobs and upload to Google Drive."""
    r = run_tailor(batch_size=batch_size, min_score=min_score, dry_run=dry_run)
    click.echo("\n" + "=" * 50)
    click.echo("  Tailor Summary")
    click.echo("=" * 50)
    for k, v in r.items():
        click.echo(f"  {k:<20}: {v}")
    click.echo("=" * 50)
