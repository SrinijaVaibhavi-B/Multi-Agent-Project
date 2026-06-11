"""CLI for the fit scorer agent."""

import click
from jobops.agents.scorer.runner import run_scorer


@click.group()
def score():
    """Fit scoring commands."""
    pass


@score.command("run")
@click.option("--batch-size", default=100, show_default=True, help="Max jobs to score per run.")
@click.option("--dry-run", is_flag=True, default=False, help="Score but do not write results to DB.")
def score_run(batch_size: int, dry_run: bool):
    """Score unscored jobs in the pipeline using rules + LLM."""
    results = run_scorer(batch_size=batch_size, dry_run=dry_run)

    click.echo("")
    click.echo("=" * 50)
    click.echo("  Scorer Summary")
    click.echo("=" * 50)
    click.echo(f"  Total processed   : {results['total']}")
    click.echo(f"  Rule rejected     : {results['rule_rejected']}")
    click.echo(f"  LLM scored        : {results['llm_scored']}")
    click.echo(f"  Queued (>= 40)    : {results['queued']}")
    click.echo(f"  Skipped (< 40)    : {results['skipped']}")
    if results["dry_run"]:
        click.echo("  (DRY RUN — no DB writes)")
    click.echo("=" * 50)
