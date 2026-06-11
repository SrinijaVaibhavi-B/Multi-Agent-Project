import click
from jobops.cli.db_cli import db
from jobops.cli.discover_cli import discover


@click.group()
def cli():
    """JobOps CLI."""
    pass


cli.add_command(db)
cli.add_command(discover)


def main():
    cli()


if __name__ == "__main__":
    main()
