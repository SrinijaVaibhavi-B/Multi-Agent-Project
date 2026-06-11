"""CLI for Apply Agent Tier 1."""

import click
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@click.group()
def apply():
    """Apply Agent — auto-submit applications via Playwright."""


@apply.command()
@click.option("--batch-size", default=10, show_default=True, help="Jobs to process per run.")
@click.option("--dry-run", is_flag=True, help="Detect ATS and log without submitting.")
def run(batch_size: int, dry_run: bool):
    """Apply to resume_ready jobs on Greenhouse, Lever, and Ashby."""
    from jobops.agents.apply.runner import run_apply
    run_apply(batch_size=batch_size, dry_run=dry_run)


@apply.command()
def migrate():
    """Add apply_result column to job_pipeline if missing."""
    import sqlite3
    import os
    db_path = os.environ.get("DB_URL", "sqlite:///jobops.db").replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("ALTER TABLE job_pipeline ADD COLUMN apply_result TEXT")
        conn.commit()
        click.echo("Column apply_result added.")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            click.echo("Column already exists.")
        else:
            raise
    finally:
        conn.close()


if __name__ == "__main__":
    apply()
