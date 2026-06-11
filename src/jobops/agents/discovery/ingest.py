"""Ingestion — maps a raw API job dict to a JobPipeline row."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from jobops.db.models import JobPipeline


def ingest_job(session: Session, job: dict, dedup_hash: str) -> JobPipeline:
    """Create and persist a JobPipeline row from a raw API job dict."""
    now = datetime.now(timezone.utc)

    pipeline = JobPipeline(
        external_job_id=str(job.get("id", "")),
        ats_platform=job.get("source") or job.get("source_type"),
        pipeline_status="discovered",
        date_discovered=now,
        raw_description=job.get("description_text", ""),
        fit_score=None,
        dedup_hash=dedup_hash,
        company_name=job.get("organization", ""),
        job_title=job.get("title", ""),
        job_url=job.get("url", ""),
    )

    session.add(pipeline)
    session.commit()
    session.refresh(pipeline)
    return pipeline
