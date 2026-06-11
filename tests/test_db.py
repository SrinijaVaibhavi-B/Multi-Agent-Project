import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from jobops.db.models import Base, Job, AnswerBank


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def test_all_tables_created(engine):
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "jobs" in tables
    assert "review_queue" in tables
    assert "answer_bank" in tables


def test_insert_and_read_job(engine):
    with Session(engine) as session:
        job = Job(
            company_name="Acme Corp",
            job_title="Software Engineer",
            job_url="https://example.com/jobs/123",
            dedup_hash="abc123",
            status="discovered",
        )
        session.add(job)
        session.commit()
        result = session.get(Job, job.id)
        assert result.company_name == "Acme Corp"
        assert result.job_title == "Software Engineer"
        assert result.status == "discovered"


def test_dedup_hash_unique_constraint(engine):
    with Session(engine) as session:
        job1 = Job(
            company_name="Acme Corp",
            job_title="Engineer",
            job_url="https://example.com/1",
            dedup_hash="samehash",
        )
        job2 = Job(
            company_name="Beta Inc",
            job_title="Developer",
            job_url="https://example.com/2",
            dedup_hash="samehash",
        )
        session.add(job1)
        session.commit()
        session.add(job2)
        with pytest.raises(IntegrityError):
            session.commit()


def test_insert_answer_bank(engine):
    with Session(engine) as session:
        entry = AnswerBank(
            question_key="work_authorization_us",
            answer_value="Yes",
            category="legal",
        )
        session.add(entry)
        session.commit()
        result = session.get(AnswerBank, entry.id)
        assert result.question_key == "work_authorization_us"
        assert result.answer_value == "Yes"
        assert result.category == "legal"
