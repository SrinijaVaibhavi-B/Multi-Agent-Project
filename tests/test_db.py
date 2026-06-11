import pytest
import hashlib
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from jobops.db.models import Base, Job, JobPipeline, AnswerBank


@pytest.fixture
def engine():
    e = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(e)
    yield e
    e.dispose()


def test_all_tables_created(engine):
    tables = inspect(engine).get_table_names()
    assert "jobs" in tables
    assert "job_pipeline" in tables
    assert "review_queue" in tables
    assert "answer_bank" in tables


def test_jobs_table_has_no_internal_fields(engine):
    cols = {c["name"] for c in inspect(engine).get_columns("jobs")}
    assert "dedup_hash" not in cols
    assert "ats_platform" not in cols
    assert "pipeline_status" not in cols


def test_insert_and_read_job(engine):
    with Session(engine) as s:
        job = Job(
            company_name="Stripe",
            job_title="Software Engineer",
            job_url="https://stripe.com/jobs/1",
            status="applied",
        )
        s.add(job)
        s.commit()
        row = s.get(Job, job.id)
        assert row.company_name == "Stripe"
        assert row.status == "applied"


def test_pipeline_dedup_hash_unique(engine):
    with Session(engine) as s:
        h = hashlib.sha256(b"greenhouse:abc").hexdigest()[:16]
        s.add(JobPipeline(dedup_hash=h, pipeline_status="discovered"))
        s.commit()
        s.add(JobPipeline(dedup_hash=h, pipeline_status="discovered"))
        with pytest.raises(IntegrityError):
            s.commit()


def test_insert_answer_bank(engine):
    with Session(engine) as s:
        s.add(AnswerBank(question_key="work_authorization_us", answer_value="yes", category="legal"))
        s.commit()
        row = s.query(AnswerBank).first()
        assert row.question_key == "work_authorization_us"
