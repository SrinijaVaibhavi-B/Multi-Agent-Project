"""CLI for the resume tailor agent."""

import click
from jobops.agents.tailor.runner import run_tailor
from jobops.agents.tailor.drive import get_auth_url, exchange_code


@click.group()
def tailor():
    """Resume tailoring commands."""
    pass


@tailor.command("auth")
def tailor_auth():
    """One-time Google Drive OAuth2 setup — get your refresh token."""
    import json
    from dotenv import load_dotenv
    load_dotenv()
    auth_url, flow = get_auth_url()
    click.echo("\n1. Open this URL in your browser:\n")
    click.echo(f"   {auth_url}\n")
    click.echo("2. Sign in with your Google account and allow access.")
    click.echo("3. Copy the authorization code shown and paste it below.\n")
    code = click.prompt("Authorization code").strip()
    token_data = exchange_code(flow, code)
    token_json = json.dumps(token_data)
    click.echo("\nAuth successful! Add this to your .env file:\n")
    click.echo(f"GOOGLE_DRIVE_TOKEN_JSON={token_json}\n")


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
