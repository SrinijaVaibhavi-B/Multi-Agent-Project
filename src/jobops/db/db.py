import os
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from jobops.db.models import Base


def init_db(db_url: str) -> None:
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    engine.dispose()


@contextmanager
def get_session():
    db_url = os.environ.get("DB_URL", "sqlite:///jobops.db")
    engine = create_engine(db_url)
    with Session(engine) as session:
        yield session
    engine.dispose()
