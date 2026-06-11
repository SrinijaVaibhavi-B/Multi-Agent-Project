"""CLI for the fit scorer agent."""

import click
from jobops.agents.scorer.runner import (
    run_scorer,
    run_scorer_parallel,
    run_scorer_batch_submit,
    run_scorer_batch_collect,
)


@click.group()
def score():
    """Fit scoring commands."""
    pass


@score.command("run")
@click.option("--batch-size", default=100, show_default=True)
@click.option("--dry-run", is_flag=True, default=False)
def score_run(batch_size, dry_run):
    """Score jobs sequentially (slow, use for testing)."""
    r = run_scorer(batch_size=batch_size, dry_run=dry_run)
    _print_summary(r)


@score.command("parallel")
@click.option("--batch-size", default=5000, show_default=True)
@click.option("--concurrency", default=20, show_default=True, help="Simultaneous LLM calls.")
@click.option("--dry-run", is_flag=True, default=False)
def score_parallel(batch_size, concurrency, dry_run):
    """Score jobs in parallel (~10-20x faster than sequential)."""
    r = run_scorer_parallel(batch_size=batch_size, concurrency=concurrency, dry_run=dry_run)
    _print_summary(r)


@score.command("batch-submit")
@click.option("--batch-size", default=5000, show_default=True)
def score_batch_submit(batch_size):
    """Submit all jobs to Anthropic Batch API (50% cheaper, async)."""
    run_scorer_batch_submit(batch_size=batch_size)


@score.command("batch-results")
@click.option("--batch-id", required=True, help="Batch ID from batch-submit.")
@click.option("--dry-run", is_flag=True, default=False)
def score_batch_results(batch_id, dry_run):
    """Collect results from a previously submitted batch."""
    r = run_scorer_batch_collect(batch_id=batch_id, dry_run=dry_run)
    if r.get("status") == "done":
        _print_summary(r)


def _print_summary(r: dict):
    click.echo("\n" + "=" * 50)
    click.echo("  Scorer Summary")
    click.echo("=" * 50)
    for k, v in r.items():
        if k != "dry_run":
            click.echo(f"  {k:<20}: {v}")
    click.echo("=" * 50)
