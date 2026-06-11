"""Scorer orchestration — sequential, parallel, and batch modes."""

import asyncio
import os
import time

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import select

from jobops.agents.scorer.rules import apply_rules
from jobops.agents.scorer.scorer import score_job, score_jobs_parallel, submit_batch, poll_batch
from jobops.db.db import get_session
from jobops.db.models import JobPipeline

_COMMIT_BATCH_SIZE = 50


def _pipeline_to_job_dict(pipeline: JobPipeline) -> dict:
    return {
        "job_title": pipeline.job_title,
        "company_name": pipeline.company_name,
        "job_url": pipeline.job_url,
        "raw_description": pipeline.raw_description,
        "ai_experience_level": None,
    }


def _load_unscored(batch_size: int) -> list[JobPipeline]:
    with get_session() as session:
        jobs = list(session.scalars(
            select(JobPipeline)
            .where(JobPipeline.pipeline_status == "discovered")
            .where(JobPipeline.fit_score.is_(None))
            .limit(batch_size)
        ).all())
    return jobs


def _flush_updates(updates: list[dict]) -> None:
    with get_session() as session:
        for u in updates:
            p = session.get(JobPipeline, u["id"])
            if p:
                p.fit_score = u["fit_score"]
                p.pipeline_status = u["pipeline_status"]
        session.commit()


def _apply_rules_pass(jobs: list[JobPipeline]) -> tuple[list[JobPipeline], list[dict]]:
    """Run rule filter. Returns (passed_jobs, rule_rejected_updates)."""
    passed, rejected_updates = [], []
    for p in jobs:
        ok, reason = apply_rules(_pipeline_to_job_dict(p))
        if not ok:
            print(f"[scorer] RULE REJECT — {p.job_title} @ {p.company_name} — {reason}")
            rejected_updates.append({"id": p.id, "fit_score": 0, "pipeline_status": "skipped"})
        else:
            passed.append(p)
    return passed, rejected_updates


def _build_summary(total, rule_rejected, llm_scored, queued, skipped) -> dict:
    return {"total": total, "rule_rejected": rule_rejected,
            "llm_scored": llm_scored, "queued": queued, "skipped": skipped}


def _status_from_score(score: int) -> str:
    return "queued" if score >= 40 else "skipped"


# ---------------------------------------------------------------------------
# Mode 1 — Sequential (original, slow)
# ---------------------------------------------------------------------------

def run_scorer(batch_size: int = 100, skip_scored: bool = True, dry_run: bool = False) -> dict:
    jobs = _load_unscored(batch_size)
    total = len(jobs)
    print(f"[scorer] Found {total} unscored jobs — sequential mode.")

    passed, rejected_updates = _apply_rules_pass(jobs)
    if not dry_run:
        _flush_updates(rejected_updates)

    counts = {"total": total, "rule_rejected": len(rejected_updates), "llm_scored": 0, "queued": 0, "skipped": 0}
    updates = []

    for idx, p in enumerate(passed, 1):
        score = score_job(_pipeline_to_job_dict(p))
        status = _status_from_score(score)
        counts["llm_scored"] += 1
        if status == "queued": counts["queued"] += 1
        else: counts["skipped"] += 1
        print(f"[scorer] [{idx}/{len(passed)}] score={score} status={status} — {p.job_title} @ {p.company_name}")
        updates.append({"id": p.id, "fit_score": score, "pipeline_status": status})
        if len(updates) >= _COMMIT_BATCH_SIZE:
            if not dry_run:
                _flush_updates(updates)
            updates.clear()
        time.sleep(0.1)

    if updates and not dry_run:
        _flush_updates(updates)

    print(f"[scorer] Done. queued={counts['queued']}, skipped={counts['skipped']}, rule_rejected={counts['rule_rejected']}")
    return counts


# ---------------------------------------------------------------------------
# Mode 2 — Parallel async (~10-20x faster)
# ---------------------------------------------------------------------------

def run_scorer_parallel(batch_size: int = 5000, concurrency: int = 20, dry_run: bool = False) -> dict:
    jobs = _load_unscored(batch_size)
    total = len(jobs)
    print(f"[scorer] Found {total} unscored jobs — parallel mode (concurrency={concurrency}).")

    passed, rejected_updates = _apply_rules_pass(jobs)
    if not dry_run:
        _flush_updates(rejected_updates)

    print(f"[scorer] Rule filter: {len(rejected_updates)} rejected, {len(passed)} passing to LLM...")

    job_dicts = [_pipeline_to_job_dict(p) for p in passed]
    scores = asyncio.run(score_jobs_parallel(job_dicts, concurrency=concurrency))

    updates = []
    queued = skipped = 0
    for p, score in zip(passed, scores):
        status = _status_from_score(score)
        if status == "queued": queued += 1
        else: skipped += 1
        updates.append({"id": p.id, "fit_score": score, "pipeline_status": status})

    if not dry_run:
        # Flush in batches
        for i in range(0, len(updates), _COMMIT_BATCH_SIZE):
            _flush_updates(updates[i:i + _COMMIT_BATCH_SIZE])

    print(f"[scorer] Done. queued={queued}, skipped={skipped}, rule_rejected={len(rejected_updates)}")
    return _build_summary(total, len(rejected_updates), len(passed), queued, skipped)


# ---------------------------------------------------------------------------
# Mode 3 — Anthropic Batch API (fire-and-forget, 50% cheaper)
# ---------------------------------------------------------------------------

def run_scorer_batch_submit(batch_size: int = 5000) -> str:
    """Submit all unscored jobs as a batch. Returns batch_id."""
    jobs = _load_unscored(batch_size)
    total = len(jobs)
    print(f"[scorer] Found {total} unscored jobs — batch submit mode.")

    passed, rejected_updates = _apply_rules_pass(jobs)
    _flush_updates(rejected_updates)
    print(f"[scorer] Rule filter: {len(rejected_updates)} rejected, {len(passed)} sending to batch API...")

    job_dicts = [_pipeline_to_job_dict(p) for p in passed]
    pipeline_ids = [p.id for p in passed]

    batch_id = submit_batch(job_dicts, pipeline_ids)
    print(f"[scorer] Batch submitted! batch_id={batch_id}")
    print(f"[scorer] Run 'score batch-results --batch-id {batch_id}' to collect results when ready (~5 min).")
    return batch_id


def run_scorer_batch_collect(batch_id: str, dry_run: bool = False) -> dict:
    """Poll a batch and write results to DB once complete."""
    print(f"[scorer] Checking batch {batch_id}...")
    is_done, results = poll_batch(batch_id)

    if not is_done:
        print("[scorer] Batch not ready yet — check back in a few minutes.")
        return {"status": "pending"}

    print(f"[scorer] Batch complete! {len(results)} results received.")

    updates = []
    queued = skipped = 0
    for pipeline_id, score in results.items():
        status = _status_from_score(score)
        if status == "queued": queued += 1
        else: skipped += 1
        updates.append({"id": pipeline_id, "fit_score": score, "pipeline_status": status})

    if not dry_run:
        for i in range(0, len(updates), _COMMIT_BATCH_SIZE):
            _flush_updates(updates[i:i + _COMMIT_BATCH_SIZE])

    print(f"[scorer] Done. queued={queued}, skipped={skipped}")
    return {"status": "done", "queued": queued, "skipped": skipped, "total": len(results)}
