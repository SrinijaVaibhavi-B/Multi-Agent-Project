import click
from jobops.cli.db_cli import db
from jobops.cli.discover_cli import discover
from jobops.cli.scorer_cli import score


@click.group()
def cli():
    """JobOps CLI."""
    pass


cli.add_command(db)
cli.add_command(discover)
cli.add_command(score)


def main():
    cli()


if __name__ == "__main__":
    main()
