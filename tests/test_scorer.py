"""Unit tests for the Fit Scorer agent."""

from unittest.mock import MagicMock, patch

import pytest

from jobops.agents.scorer.rules import (
    apply_rules,
    check_domain_exclusions,
    check_yoe,
)


# ---------------------------------------------------------------------------
# check_yoe tests
# ---------------------------------------------------------------------------

def test_check_yoe_accepts_1_to_5():
    """None, 0-1, 1-2, 2-5 should all pass."""
    for level in (None, "0-1", "1-2", "2-5"):
        job = {"ai_experience_level": level}
        passed, reason = check_yoe(job)
        assert passed, f"Expected {level!r} to pass, got reason: {reason}"
        assert reason == "ok"


def test_check_yoe_rejects_senior():
    """5-10 and 10+ should be rejected."""
    for level in ("5-10", "10+"):
        job = {"ai_experience_level": level}
        passed, reason = check_yoe(job)
        assert not passed, f"Expected {level!r} to fail"
        assert "yoe_too_senior" in reason


# ---------------------------------------------------------------------------
# check_domain_exclusions tests
# ---------------------------------------------------------------------------

def test_domain_exclusion_rejects_firmware():
    """Job title containing 'Firmware Engineer' should be rejected."""
    passed, reason = check_domain_exclusions("Firmware Engineer", "Write low-level code.")
    assert not passed
    assert "domain_excluded" in reason


def test_domain_exclusion_rejects_fpga():
    """Description containing 'FPGA design' should be rejected."""
    passed, reason = check_domain_exclusions(
        "Hardware Engineer",
        "Responsibilities include FPGA design and synthesis.",
    )
    assert not passed
    assert "domain_excluded" in reason


def test_domain_exclusion_keeps_gpu_user():
    """Using GPUs for ML training should NOT be excluded."""
    passed, reason = check_domain_exclusions(
        "Machine Learning Engineer",
        "We train large language models on GPU clusters using PyTorch. "
        "Experience with GPU accelerated workloads is a plus.",
    )
    assert passed, f"Expected GPU-user role to pass, got: {reason}"
    assert reason == "ok"


def test_domain_exclusion_keeps_ai_role():
    """Standard AI Engineer role with normal ML description should pass."""
    passed, reason = check_domain_exclusions(
        "AI Engineer",
        "Build and deploy machine learning models. Work with transformers, "
        "LLMs, and modern ML infrastructure. Python, PyTorch, and cloud experience required.",
    )
    assert passed, f"Expected AI Engineer role to pass, got: {reason}"
    assert reason == "ok"


# ---------------------------------------------------------------------------
# apply_rules tests
# ---------------------------------------------------------------------------

def test_apply_rules_full_pass():
    """A good SWE job should pass all checks."""
    job = {
        "ai_experience_level": "1-2",
        "job_title": "Software Engineer",
        "company_name": "Acme Corp",
        "raw_description": "Build web applications with Python and React. 1-3 years experience.",
    }
    passed, reason = apply_rules(job)
    assert passed
    assert reason == "ok"


def test_apply_rules_fails_yoe():
    """A 10+ YOE job should fail the YOE check."""
    job = {
        "ai_experience_level": "10+",
        "job_title": "Principal Engineer",
        "company_name": "BigCorp",
        "raw_description": "Lead architecture for large systems.",
    }
    passed, reason = apply_rules(job)
    assert not passed
    assert "yoe_too_senior" in reason


def test_apply_rules_fails_domain():
    """An embedded role should fail the domain exclusion check."""
    job = {
        "ai_experience_level": "2-5",
        "job_title": "Embedded Systems Engineer",
        "company_name": "IoT Startup",
        "raw_description": "Write firmware for IoT devices.",
    }
    passed, reason = apply_rules(job)
    assert not passed
    assert "domain_excluded" in reason


# ---------------------------------------------------------------------------
# runner tests
# ---------------------------------------------------------------------------

def _make_pipeline(
    id: int,
    job_title: str,
    company_name: str,
    raw_description: str,
    pipeline_status: str = "discovered",
    fit_score=None,
):
    """Create a mock JobPipeline ORM object."""
    obj = MagicMock()
    obj.id = id
    obj.job_title = job_title
    obj.company_name = company_name
    obj.raw_description = raw_description
    obj.job_url = "https://example.com/job"
    obj.pipeline_status = pipeline_status
    obj.fit_score = fit_score
    return obj


def _make_mock_session(jobs):
    """Create a mock session that returns the given jobs on scalars query and supports get()."""
    mock_session = MagicMock()
    mock_session.scalars.return_value.all.return_value = jobs
    mock_session.get.side_effect = lambda model, id: next(
        (j for j in jobs if j.id == id), None
    )
    return mock_session


def _make_ctx_manager(mock_session):
    """Return a context manager mock that yields mock_session on every call."""
    def factory():
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=mock_session)
        ctx.__exit__ = MagicMock(return_value=False)
        return ctx
    return factory


def test_runner_scores_unscored_jobs():
    """Mock DB with 3 unscored jobs, mock score_job returning 75, verify fit_score and status."""
    import jobops.agents.scorer.runner as runner_mod  # ensure module is imported

    mock_jobs = [
        _make_pipeline(1, "Software Engineer", "Acme", "Build web apps with Python. 1-3 YOE."),
        _make_pipeline(2, "Backend Engineer", "Startup", "REST APIs, databases, cloud infra."),
        _make_pipeline(3, "Full Stack Dev", "TechCo", "React + Node.js, modern web stack."),
    ]

    mock_session = _make_mock_session(mock_jobs)

    with (
        patch.object(runner_mod, "get_session", side_effect=_make_ctx_manager(mock_session)),
        patch.object(runner_mod, "score_job", return_value=75) as mock_score,
        patch.object(runner_mod.time, "sleep"),
    ):
        result = runner_mod.run_scorer(batch_size=100, dry_run=False)

    assert result["total"] == 3
    assert result["llm_scored"] == 3
    assert result["queued"] == 3
    assert result["rule_rejected"] == 0

    # Verify score_job was called 3 times
    assert mock_score.call_count == 3

    # Each job should have been retrieved for update via session.get
    fetched_ids = [call[0][1] for call in mock_session.get.call_args_list]
    for job in mock_jobs:
        assert job.id in fetched_ids


def test_runner_skips_rule_failures():
    """Job failing domain check should get fit_score=0 and status='skipped'."""
    import jobops.agents.scorer.runner as runner_mod  # ensure module is imported

    mock_jobs = [
        _make_pipeline(
            1,
            "Firmware Engineer",
            "Hardware Co",
            "Write firmware for embedded devices using RTOS.",
        ),
    ]

    mock_session = _make_mock_session(mock_jobs)

    with (
        patch.object(runner_mod, "get_session", side_effect=_make_ctx_manager(mock_session)),
        patch.object(runner_mod, "score_job") as mock_score,
        patch.object(runner_mod.time, "sleep"),
    ):
        result = runner_mod.run_scorer(batch_size=100, dry_run=False)

    # LLM should NOT have been called
    mock_score.assert_not_called()

    assert result["rule_rejected"] == 1
    assert result["llm_scored"] == 0

    # The ORM object should have been updated with score=0 and status=skipped
    job = mock_jobs[0]
    assert job.fit_score == 0
    assert job.pipeline_status == "skipped"
