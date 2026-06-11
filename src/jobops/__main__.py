import click
from jobops.cli.db_cli import db
from jobops.cli.discover_cli import discover
from jobops.cli.scorer_cli import score
from jobops.cli.tailor_cli import tailor


@click.group()
def cli():
    """JobOps CLI."""
    pass


cli.add_command(db)
cli.add_command(discover)
cli.add_command(score)
cli.add_command(tailor)


def main():
    cli()


if __name__ == "__main__":
    main()
