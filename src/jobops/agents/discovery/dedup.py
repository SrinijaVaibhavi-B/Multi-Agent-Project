"""Deduplication helpers."""

import hashlib

from sqlalchemy.orm import Session

from jobops.db.models import JobPipeline


def compute_dedup_hash(job: dict) -> str:
    """Return a 32-char SHA256 hash unique to this job listing."""
    source_type = job.get("source_type", "")
    source_domain = job.get("source_domain", "")
    job_id = str(job.get("id", ""))
    raw = f"{source_type}:{source_domain}:{job_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def is_duplicate(session: Session, dedup_hash: str) -> bool:
    """Return True if this dedup_hash already exists in job_pipeline."""
    exists = session.query(JobPipeline).filter_by(dedup_hash=dedup_hash).first()
    return exists is not None
