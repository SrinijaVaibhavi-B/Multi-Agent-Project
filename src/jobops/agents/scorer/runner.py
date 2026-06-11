"""Scorer agent orchestration — score unscored jobs in the pipeline."""

import time

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import select

from jobops.agents.scorer.rules import apply_rules
from jobops.agents.scorer.scorer import score_job
from jobops.db.db import get_session
from jobops.db.models import JobPipeline

_COMMIT_BATCH_SIZE = 50
_PROGRESS_INTERVAL = 25
_RATE_LIMIT_SLEEP = 0.1  # seconds between LLM calls


def _pipeline_to_job_dict(pipeline: JobPipeline) -> dict:
    """Convert a JobPipeline ORM object to a plain dict for rules/scorer."""
    return {
        "job_title": pipeline.job_title,
        "company_name": pipeline.company_name,
        "job_url": pipeline.job_url,
        "raw_description": pipeline.raw_description,
        # ai_experience_level is not stored on JobPipeline; default to None (unknown — keep it)
        "ai_experience_level": None,
    }


def run_scorer(
    batch_size: int = 100,
    skip_scored: bool = True,
    dry_run: bool = False,
) -> dict:
    """
    Score unscored jobs in the pipeline.

    1. Load up to `batch_size` unscored jobs (fit_score IS NULL, status='discovered').
    2. For each job:
       a. Run apply_rules() — if fails, set fit_score=0, pipeline_status='skipped'.
       b. If passes, run score_job() — set fit_score to result.
    3. If fit_score < 40: set pipeline_status='skipped'.
    4. If fit_score >= 40: set pipeline_status='queued'.
    5. Commit in batches of 50.
    6. Print progress every 25 jobs.

    Returns a summary dict with counts.
    """
    with get_session() as session:
        query = (
            select(JobPipeline)
            .where(JobPipeline.pipeline_status == "discovered")
        )
        if skip_scored:
            query = query.where(JobPipeline.fit_score.is_(None))

        query = query.limit(batch_size)
        jobs = list(session.scalars(query).all())

    total = len(jobs)
    print(f"[scorer] Found {total} unscored jobs to process.")

    counts = {
        "total": total,
        "rule_rejected": 0,
        "llm_scored": 0,
        "queued": 0,
        "skipped": 0,
        "dry_run": dry_run,
    }

    pending_updates: list[dict] = []  # {id, fit_score, pipeline_status}

    for idx, pipeline in enumerate(jobs, start=1):
        job_dict = _pipeline_to_job_dict(pipeline)

        passed_rules, rule_reason = apply_rules(job_dict)

        if not passed_rules:
            fit_score = 0
            new_status = "skipped"
            counts["rule_rejected"] += 1
            print(f"[scorer] [{idx}/{total}] RULE REJECT — {pipeline.job_title} @ {pipeline.company_name} — {rule_reason}")
        else:
            fit_score = score_job(job_dict)
            counts["llm_scored"] += 1
            time.sleep(_RATE_LIMIT_SLEEP)

            if fit_score >= 40:
                new_status = "queued"
                counts["queued"] += 1
            else:
                new_status = "skipped"
                counts["skipped"] += 1

            print(
                f"[scorer] [{idx}/{total}] score={fit_score} status={new_status} — "
                f"{pipeline.job_title} @ {pipeline.company_name}"
            )

        pending_updates.append({
            "id": pipeline.id,
            "fit_score": fit_score,
            "pipeline_status": new_status,
        })

        if idx % _PROGRESS_INTERVAL == 0:
            print(f"[scorer] Progress: {idx}/{total} processed.")

        # Commit in batches
        if len(pending_updates) >= _COMMIT_BATCH_SIZE:
            if not dry_run:
                _flush_updates(pending_updates)
            pending_updates.clear()

    # Flush remaining
    if pending_updates and not dry_run:
        _flush_updates(pending_updates)
    elif pending_updates and dry_run:
        print(f"[scorer] DRY RUN — would update {len(pending_updates)} remaining jobs.")

    if dry_run:
        print(f"[scorer] DRY RUN complete — no DB writes performed.")
    else:
        print(f"[scorer] Done. queued={counts['queued']}, skipped={counts['skipped']}, rule_rejected={counts['rule_rejected']}")

    return counts


def _flush_updates(updates: list[dict]) -> None:
    """Write a batch of fit_score/pipeline_status updates to the DB."""
    with get_session() as session:
        for update in updates:
            pipeline = session.get(JobPipeline, update["id"])
            if pipeline is not None:
                pipeline.fit_score = update["fit_score"]
                pipeline.pipeline_status = update["pipeline_status"]
        session.commit()
