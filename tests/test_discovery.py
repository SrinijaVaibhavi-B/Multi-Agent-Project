"""Unit tests for the discovery agent — no real API calls."""

import hashlib
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from jobops.db.models import Base, JobPipeline
from jobops.agents.discovery.filters import (
    is_target_role,
    is_staffing_firm,
    compute_ghost_score,
    should_include,
)
from jobops.agents.discovery.dedup import compute_dedup_hash, is_duplicate
from jobops.agents.discovery.ingest import ingest_job


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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


def _make_job(**overrides) -> dict:
    """Return a minimal job dict matching the real API structure."""
    base = {
        "id": 2200367755,
        "date_posted": datetime.now(timezone.utc).isoformat(),
        "date_created": datetime.now(timezone.utc).isoformat(),
        "title": "Applied AI Engineer, Audio, XR",
        "organization": "Stripe",
        "organization_url": "https://stripe.com",
        "url": "https://boards.greenhouse.io/stripe/jobs/123",
        "source_type": "ats",
        "source": "in-house",
        "source_domain": "stripe.com",
        "locations_derived": ["Mountain View, California, United States"],
        "countries_derived": ["United States"],
        "ai_salary_min_value": 159000,
        "ai_salary_max_value": 231000,
        "ai_salary_currency": "USD",
        "ai_experience_level": "2-5",
        "ai_work_arrangement": "On-site",
        "ai_visa_sponsorship": False,
        "ai_key_skills": ["Machine Learning", "Python", "C++"],
        "description_text": "MINIMUM QUALIFICATIONS: Bachelor degree in CS. "
                            "Experience with machine learning frameworks. "
                            "Strong knowledge of Python and C++. "
                            "Ability to work on XR and audio technology stacks.",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# is_target_role
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("title,expected", [
    # Should include
    ("Software Engineer", True),
    ("Senior Software Engineer", True),
    ("Full Stack Engineer", True),
    ("Backend Engineer", True),
    ("Frontend Engineer", True),
    ("AI Engineer", True),
    ("Applied AI Engineer", True),
    ("ML Engineer", True),
    ("Platform Engineer", True),
    ("Engineering Manager", True),
    ("Staff Engineer, Payments", True),
    # Should exclude
    ("Data Scientist", False),
    ("Data Analyst", False),
    ("Product Manager", False),
    ("UX Designer", False),
    ("Research Scientist", False),
    ("QA Engineer", False),
    ("Developer Advocate", False),
    ("Sales Engineer", False),
    ("Recruiter", False),
    ("ML Research Scientist", False),
    ("Consultant, Software", False),
    ("Program Manager", False),
])
def test_is_target_role(title, expected):
    assert is_target_role(title) == expected, f"is_target_role({title!r}) should be {expected}"


# ---------------------------------------------------------------------------
# is_staffing_firm
# ---------------------------------------------------------------------------

def test_staffing_firm_by_domain():
    assert is_staffing_firm("TEKsystems", "teksystems.com") is True


def test_staffing_firm_by_name_keyword():
    assert is_staffing_firm("Apex Staffing Group", "apexstaffing.com") is True
    assert is_staffing_firm("Global Talent Solutions", "globaltalent.io") is True
    assert is_staffing_firm("Randstad North America", "randstad.com") is True


def test_not_staffing_firm():
    assert is_staffing_firm("Stripe", "stripe.com") is False
    assert is_staffing_firm("Stripe", "stripe.com") is False
    assert is_staffing_firm("Notion Labs", "notion.so") is False


# ---------------------------------------------------------------------------
# compute_ghost_score
# ---------------------------------------------------------------------------

def test_ghost_score_fresh_job():
    job = _make_job(
        date_posted=datetime.now(timezone.utc).isoformat(),
        description_text="A" * 500,
        ai_visa_sponsorship=True,
        ai_salary_min_value=100000,
    )
    score = compute_ghost_score(job)
    assert score <= 10, f"Fresh job should have low ghost score, got {score}"


def test_ghost_score_old_job():
    old_date = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    job = _make_job(
        date_posted=old_date,
        description_text="",
        ai_visa_sponsorship=False,
        ai_salary_min_value=None,
        ai_salary_max_value=None,
    )
    score = compute_ghost_score(job)
    # +40 (>30 days) +25 (short desc) +5 (no visa, no salary) = 70
    assert score >= 70, f"Old/empty job should have high ghost score, got {score}"


def test_ghost_score_generic_title():
    job = _make_job(
        title="Software Engineer",
        date_posted=datetime.now(timezone.utc).isoformat(),
        description_text="A" * 500,
        ai_visa_sponsorship=True,
        ai_salary_min_value=100000,
    )
    score = compute_ghost_score(job)
    assert score >= 10, "Generic title should add at least 10 points"


# ---------------------------------------------------------------------------
# compute_dedup_hash
# ---------------------------------------------------------------------------

def test_dedup_hash_deterministic():
    job = _make_job()
    h1 = compute_dedup_hash(job)
    h2 = compute_dedup_hash(job)
    assert h1 == h2


def test_dedup_hash_format():
    job = _make_job()
    h = compute_dedup_hash(job)
    assert len(h) == 32
    assert h == hashlib.sha256(b"ats:stripe.com:2200367755").hexdigest()[:32]


def test_dedup_hash_different_jobs():
    job1 = _make_job(id=111)
    job2 = _make_job(id=222)
    assert compute_dedup_hash(job1) != compute_dedup_hash(job2)


# ---------------------------------------------------------------------------
# is_duplicate
# ---------------------------------------------------------------------------

def test_is_duplicate_false_when_not_present(session):
    job = _make_job()
    h = compute_dedup_hash(job)
    assert is_duplicate(session, h) is False


def test_is_duplicate_true_after_insert(session):
    job = _make_job()
    h = compute_dedup_hash(job)
    session.add(JobPipeline(dedup_hash=h, pipeline_status="discovered"))
    session.commit()
    assert is_duplicate(session, h) is True


# ---------------------------------------------------------------------------
# should_include master filter
# ---------------------------------------------------------------------------

def test_should_include_passing_job():
    job = _make_job()
    include, reason = should_include(job)
    assert include is True
    assert reason == "ok"


def test_should_include_role_mismatch():
    job = _make_job(title="Data Scientist")
    include, reason = should_include(job)
    assert include is False
    assert reason == "role_mismatch"


def test_should_include_staffing_firm():
    job = _make_job(organization="Global Staffing Inc", source_domain="globalstaffing.com")
    include, reason = should_include(job)
    assert include is False
    assert reason == "staffing_firm"


def test_should_include_ghost_job():
    old_date = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    job = _make_job(
        title="Software Engineer",
        date_posted=old_date,
        description_text="Short.",
        ai_visa_sponsorship=False,
        ai_salary_min_value=None,
        ai_salary_max_value=None,
    )
    include, reason = should_include(job)
    # ghost_score = 40+25+10+5 = 80 > 70
    assert include is False
    assert reason == "likely_ghost"


# ---------------------------------------------------------------------------
# ingest_job
# ---------------------------------------------------------------------------

def test_ingest_job_creates_row(session):
    job = _make_job()
    h = compute_dedup_hash(job)
    pipeline = ingest_job(session, job, h)

    assert pipeline.id is not None
    assert pipeline.external_job_id == str(job["id"])
    assert pipeline.dedup_hash == h
    assert pipeline.pipeline_status == "discovered"
    assert pipeline.company_name == "Stripe"
    assert pipeline.job_title == "Applied AI Engineer, Audio, XR"
    assert pipeline.job_url == job["url"]
    assert pipeline.raw_description == job["description_text"]
    assert pipeline.fit_score is None


def test_ingest_job_maps_ats_platform(session):
    job = _make_job(source="greenhouse", source_type="ats")
    h = compute_dedup_hash(job)
    pipeline = ingest_job(session, job, h)
    # source takes priority over source_type
    assert pipeline.ats_platform == "greenhouse"


def test_ingest_job_persisted_in_db(session):
    job = _make_job(id=9999999)
    h = compute_dedup_hash(job)
    ingest_job(session, job, h)
    row = session.query(JobPipeline).filter_by(dedup_hash=h).first()
    assert row is not None
    assert row.external_job_id == "9999999"
