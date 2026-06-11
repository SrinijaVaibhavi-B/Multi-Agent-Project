import pytest
import hashlib
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from jobops.db.models import Base, Job, JobPipeline, StatusHistory, ReviewQueue, Outreach, AnswerBank


@pytest.fixture
def engine():
    e = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(e)
    yield e
    e.dispose()


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


def test_all_tables_created(engine):
    tables = inspect(engine).get_table_names()
    for t in ["jobs", "job_pipeline", "status_history", "review_queue", "outreach", "answer_bank"]:
        assert t in tables


def test_jobs_has_no_internal_fields(engine):
    cols = {c["name"] for c in inspect(engine).get_columns("jobs")}
    assert "dedup_hash" not in cols
    assert "ats_platform" not in cols
    assert "pipeline_status" not in cols


def test_insert_and_read_job(session):
    job = Job(company_name="Stripe", job_title="Software Engineer", job_url="https://stripe.com/jobs/1", status="applied")
    session.add(job)
    session.commit()
    row = session.get(Job, job.id)
    assert row.company_name == "Stripe"
    assert row.status == "applied"


def test_status_history_tracks_changes(session):
    job = Job(company_name="Notion", job_title="Backend Engineer", job_url="https://notion.com/jobs/1", status="applied")
    session.add(job)
    session.flush()
    session.add(StatusHistory(job_id=job.id, from_status=None, to_status="applied", changed_by="apply_agent"))
    session.add(StatusHistory(job_id=job.id, from_status="applied", to_status="screening", changed_by="inbox_monitor"))
    session.commit()
    history = session.query(StatusHistory).filter_by(job_id=job.id).all()
    assert len(history) == 2
    assert history[0].to_status == "applied"
    assert history[1].from_status == "applied"
    assert history[1].to_status == "screening"


def test_pipeline_dedup_hash_unique(session):
    h = hashlib.sha256(b"greenhouse:abc").hexdigest()[:16]
    session.add(JobPipeline(dedup_hash=h, pipeline_status="discovered"))
    session.commit()
    session.add(JobPipeline(dedup_hash=h, pipeline_status="discovered"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_review_queue_links_pipeline_and_job(session):
    job = Job(company_name="Linear", job_title="SWE", job_url="https://linear.app/jobs/1", status="applied")
    session.add(job)
    session.flush()
    pipeline = JobPipeline(dedup_hash="abc123", pipeline_status="applying", job_id=job.id)
    session.add(pipeline)
    session.flush()
    # review item before apply — linked to pipeline only
    session.add(ReviewQueue(pipeline_id=pipeline.id, reason="captcha"))
    # review item after apply — linked to job
    session.add(ReviewQueue(job_id=job.id, reason="legal_question"))
    session.commit()
    assert session.query(ReviewQueue).count() == 2


def test_outreach_linked_to_job(session):
    job = Job(company_name="Figma", job_title="Engineer", job_url="https://figma.com/jobs/1", status="applied")
    session.add(job)
    session.flush()
    session.add(Outreach(job_id=job.id, recruiter_email="recruiter@figma.com", company_name="Figma", message_subject="Hello"))
    session.commit()
    row = session.query(Outreach).first()
    assert row.company_name == "Figma"
    assert row.job.company_name == "Figma"


def test_answer_bank_unique_key(session):
    session.add(AnswerBank(question_key="work_authorization_us", answer_value="yes", category="legal"))
    session.commit()
    session.add(AnswerBank(question_key="work_authorization_us", answer_value="no", category="legal"))
    with pytest.raises(IntegrityError):
        session.commit()
