"""Apply Agent Tier 1 runner — Greenhouse, Lever, Ashby."""

import logging
import os

from playwright.sync_api import sync_playwright

from jobops.agents.apply.base import load_profile
from jobops.agents.apply.downloader import download_resume
from jobops.agents.apply.greenhouse import apply_greenhouse
from jobops.agents.apply.lever import apply_lever
from jobops.agents.apply.ashby import apply_ashby
from jobops.db.db import get_session
from jobops.db.models import JobPipeline

logger = logging.getLogger(__name__)

_ATS_HANDLERS = {
    "greenhouse": apply_greenhouse,
    "lever": apply_lever,
    "ashby": apply_ashby,
}

_ATS_URL_PATTERNS = {
    "greenhouse": ["greenhouse.io", "boards.greenhouse.io"],
    "lever": ["jobs.lever.co", "lever.co"],
    "ashby": ["ashbyhq.com", "jobs.ashbyhq.com"],
}

# Stealth init script — masks navigator.webdriver and other bot signals
_STEALTH_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    window.chrome = { runtime: {} };
    Object.defineProperty(navigator, 'permissions', {
        get: () => ({ query: () => Promise.resolve({ state: 'granted' }) })
    });
"""


def _detect_ats(job_url: str) -> str | None:
    url = job_url.lower()
    for ats, patterns in _ATS_URL_PATTERNS.items():
        if any(p in url for p in patterns):
            return ats
    return None


def _make_context(pw):
    """Create a stealth Playwright browser context."""
    browser = pw.chromium.launch(
        headless=True,
        args=[
            "--ignore-certificate-errors",
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    )
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        ignore_https_errors=True,
        viewport={"width": 1280, "height": 900},
        locale="en-US",
        timezone_id="America/New_York",
    )
    context.add_init_script(_STEALTH_SCRIPT)

    # Use playwright-stealth if available
    try:
        from playwright_stealth import stealth_sync
        _stealth_fn = stealth_sync
    except ImportError:
        _stealth_fn = None

    return browser, context, _stealth_fn


def run_apply(batch_size: int = 10, dry_run: bool = False) -> None:
    """
    Process jobs in resume_ready state and apply via Playwright.
    Updates pipeline_status to applied / review_needed / failed.
    """
    profile = load_profile()

    with get_session() as session:
        jobs = (
            session.query(JobPipeline)
            .filter(JobPipeline.pipeline_status == "resume_ready")
            .limit(batch_size)
            .all()
        )

    if not jobs:
        logger.info("No jobs in resume_ready state.")
        return

    logger.info("Processing %d jobs (dry_run=%s)", len(jobs), dry_run)

    with sync_playwright() as pw:
        browser, context, stealth_fn = _make_context(pw)

        for job in jobs:
            job_url = job.job_url
            ats = _detect_ats(job_url)

            if ats not in _ATS_HANDLERS:
                logger.info("Skipping %s — unsupported ATS (url=%s)", job.id, job_url)
                _update_status(job.id, "review_needed", f"Unsupported ATS: {job_url}")
                continue

            try:
                if job.resume_drive_url:
                    resume_path = download_resume(job.resume_drive_url)
                else:
                    logger.warning("No resume_drive_url for job %s — skipping", job.id)
                    _update_status(job.id, "review_needed", "No resume uploaded")
                    continue

                if dry_run:
                    logger.info("[dry-run] Would apply to %s via %s", job_url, ats)
                    continue

                page = context.new_page()
                if stealth_fn:
                    stealth_fn(page)
                try:
                    handler = _ATS_HANDLERS[ats]
                    jd_snippet = (job.raw_description or "")[:800]
                    result, reason = handler(page, job_url, resume_path, profile, jd_snippet=jd_snippet)
                    logger.info("Job %s → %s (%s)", job.id, result, reason[:120])
                    _update_status(job.id, result, reason)
                finally:
                    page.close()

            except Exception as e:
                logger.error("Job %s failed: %s", job.id, e)
                _update_status(job.id, "failed", str(e))

        context.close()
        browser.close()


def _update_status(job_id: int, status: str, reason: str) -> None:
    with get_session() as session:
        job = session.query(JobPipeline).filter(JobPipeline.id == job_id).first()
        if job:
            job.pipeline_status = status
            job.apply_result = reason[:500] if reason else None
            session.commit()
