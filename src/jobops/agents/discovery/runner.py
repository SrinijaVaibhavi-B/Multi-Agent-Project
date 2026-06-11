"""Discovery agent orchestration — fetch, filter, dedup, and ingest jobs."""

from dotenv import load_dotenv
load_dotenv()

from jobops.agents.discovery.client import fetch_ats_jobs, fetch_jb_jobs
from jobops.agents.discovery.filters import should_include
from jobops.agents.discovery.dedup import compute_dedup_hash, is_duplicate
from jobops.agents.discovery.ingest import ingest_job
from jobops.db.db import get_session

_TITLE_FILTER = (
    '"Software Engineer" OR "Full Stack Engineer" OR "AI Engineer" OR '
    '"Applied AI Engineer" OR "Backend Engineer" OR "Frontend Engineer" OR '
    '"Platform Engineer" OR "Product Engineer"'
)


def run_discovery(
    dry_run: bool = False,
    time_frame: str = "24h",
    location: str = "United States",
) -> dict:
    """
    Main discovery pipeline:
    1. Fetch from active-ats and active-jb endpoints (paginated).
    2. Filter each job with should_include().
    3. Dedup against job_pipeline table.
    4. Ingest non-duplicate passing jobs (unless dry_run).
    Returns a dict with counts.
    """
    print(f"[discovery] Fetching ATS jobs (time_frame={time_frame}, location={location}) ...")
    ats_jobs = fetch_ats_jobs(
        time_frame=time_frame,
        title_filter=_TITLE_FILTER,
        location=location,
    )
    print(f"[discovery] Fetching JB jobs ...")
    jb_jobs = fetch_jb_jobs(
        time_frame=time_frame,
        title_filter=_TITLE_FILTER,
        location=location,
    )

    all_jobs = ats_jobs + jb_jobs
    total_fetched = len(all_jobs)
    print(f"[discovery] Total fetched: {total_fetched} (ats={len(ats_jobs)}, jb={len(jb_jobs)})")

    passed: list[dict] = []
    filter_counts: dict[str, int] = {}
    for job in all_jobs:
        include, reason = should_include(job)
        if include:
            passed.append(job)
        else:
            filter_counts[reason] = filter_counts.get(reason, 0) + 1

    total_passed = len(passed)
    total_filtered = total_fetched - total_passed
    print(f"[discovery] Passed filters: {total_passed} | Filtered out: {total_filtered} {filter_counts}")

    duplicates_skipped = 0
    inserted = 0

    with get_session() as session:
        for job in passed:
            dedup_hash = compute_dedup_hash(job)
            if is_duplicate(session, dedup_hash):
                duplicates_skipped += 1
                continue
            if not dry_run:
                ingest_job(session, job, dedup_hash)
            inserted += 1

    if dry_run:
        print(f"[discovery] DRY RUN — would insert {inserted}, duplicates skipped {duplicates_skipped}")
    else:
        print(f"[discovery] Inserted: {inserted} | Duplicates skipped: {duplicates_skipped}")

    return {
        "total_fetched": total_fetched,
        "total_passed": total_passed,
        "total_filtered": total_filtered,
        "duplicates_skipped": duplicates_skipped,
        "inserted": inserted,
        "dry_run": dry_run,
    }
