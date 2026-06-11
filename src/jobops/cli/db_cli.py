import os
import click
from jobops.db.db import init_db


@click.group()
def cli():
    pass


@cli.group()
def db():
    pass


@db.command("init")
def db_init():
    db_url = os.environ.get("DB_URL", "sqlite:///jobops.db")
    init_db(db_url)
    click.echo(f"DB initialized at {db_url}")


def main():
    cli()


if __name__ == "__main__":
    main()
