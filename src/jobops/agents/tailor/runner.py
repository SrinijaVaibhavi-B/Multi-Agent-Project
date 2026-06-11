"""Resume tailor orchestration — processes queued jobs."""

import os
import tempfile

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import select

from jobops.agents.tailor.tailor import tailor_resume, verify_resume, _load_facts
from jobops.agents.tailor.renderer import render_pdf
from jobops.agents.tailor.drive import upload_resume
from jobops.db.db import get_session
from jobops.db.models import JobPipeline

_RESUMES_DIR = os.path.join(os.path.dirname(__file__), "../../../../resumes")


def _load_queued(batch_size: int) -> list[JobPipeline]:
    with get_session() as session:
        return list(session.scalars(
            select(JobPipeline)
            .where(JobPipeline.pipeline_status == "queued")
            .where(JobPipeline.resume_drive_url.is_(None))
            .order_by(JobPipeline.fit_score.desc())
            .limit(batch_size)
        ).all())


def _save_result(pipeline_id: int, drive_url: str, status: str) -> None:
    with get_session() as session:
        p = session.get(JobPipeline, pipeline_id)
        if p:
            p.resume_drive_url = drive_url
            p.pipeline_status = status
            session.commit()


def run_tailor(batch_size: int = 10, dry_run: bool = False, min_score: int = 60) -> dict:
    """Tailor resumes for top queued jobs. Returns summary dict."""
    jobs = _load_queued(batch_size)
    # Filter by min score
    jobs = [j for j in jobs if (j.fit_score or 0) >= min_score]
    total = len(jobs)
    print(f"[tailor] {total} jobs to tailor (score >= {min_score}, batch_size={batch_size})")

    facts = _load_facts()
    counts = {"total": total, "success": 0, "verify_warned": 0, "failed": 0}

    for idx, p in enumerate(jobs, 1):
        print(f"[tailor] [{idx}/{total}] {p.job_title} @ {p.company_name} (score={p.fit_score})")

        job_dict = {
            "job_title": p.job_title,
            "company_name": p.company_name,
            "job_url": p.job_url,
            "raw_description": p.raw_description,
        }

        # 1. Tailor
        tailored = tailor_resume(job_dict)
        if not tailored:
            print(f"[tailor]   FAILED — LLM returned nothing")
            counts["failed"] += 1
            continue

        # 2. Verify
        passed, issues = verify_resume(tailored, facts)
        if not passed:
            print(f"[tailor]   VERIFY WARN — {len(issues)} issue(s):")
            for issue in issues:
                print(f"[tailor]     ! {issue}")
            counts["verify_warned"] += 1

        if dry_run:
            print(f"[tailor]   DRY RUN — skipping PDF + upload")
            counts["success"] += 1
            continue

        # 3. Render PDF
        safe_company = "".join(c for c in (p.company_name or "company") if c.isalnum() or c in "-_ ")[:30]
        safe_title = "".join(c for c in (p.job_title or "role") if c.isalnum() or c in "-_ ")[:30]
        filename = f"{safe_company} - {safe_title} - Srinija Vaibhavi.pdf"

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            render_pdf(tailored, tmp_path)
            print(f"[tailor]   PDF rendered → {tmp_path}")

            # 4. Upload to Drive
            drive_url = upload_resume(tmp_path, filename)
            print(f"[tailor]   Uploaded → {drive_url}")

            _save_result(p.id, drive_url, "resume_ready")
            counts["success"] += 1

        except Exception as e:
            print(f"[tailor]   ERROR during render/upload: {e}")
            counts["failed"] += 1
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    print(f"[tailor] Done. success={counts['success']}, warned={counts['verify_warned']}, failed={counts['failed']}")
    return counts
