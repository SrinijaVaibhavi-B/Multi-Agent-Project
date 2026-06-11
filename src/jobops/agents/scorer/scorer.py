"""LLM-based fit scoring — sequential, parallel async, and batch API modes."""

import asyncio
import json
import os
import time

import anthropic

_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 100
_DESCRIPTION_TRUNCATE = 1500

_SYSTEM_PROMPT = """You are a job fit evaluator. You assess how well a software engineering job matches a candidate profile.

Candidate profile:
- 3 years of experience as a software engineer
- Flexible on tech stack (can tailor resume to any language/framework)
- Seeking roles that prefer 1-5 YOE (junior to mid-level)
- Open to any industry, any location, any work arrangement (remote/hybrid/onsite)
- Interested in: SWE, fullstack, backend, frontend, AI/ML, platform, product engineering

Scoring rubric:
- 80-100: Great fit — clear SWE/fullstack/AI role, 1-5 YOE preferred, interesting company
- 60-79: Good fit — matches well but minor concerns (slightly senior-leaning, niche stack)
- 40-59: Weak fit — possible stretch (5+ YOE preferred but not required, or very specialized domain)
- 0-39: Poor fit — wrong level, wrong domain, or too vague to evaluate

Respond ONLY with a JSON object in this exact format (no other text):
{"score": <integer 0-100>, "reason": "<one sentence explaining the score>"}"""


def _build_user_message(job: dict) -> str:
    title = job.get("job_title") or "Unknown Title"
    company = job.get("company_name") or "Unknown Company"
    description = job.get("raw_description") or ""
    if len(description) > _DESCRIPTION_TRUNCATE:
        description = description[:_DESCRIPTION_TRUNCATE] + "... [truncated]"
    return f"Job Title: {title}\nCompany: {company}\n\nJob Description:\n{description}\n\nEvaluate this job's fit for the candidate and return a JSON score."


def _parse_score(text: str) -> int:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        parsed = json.loads(text)
        return max(0, min(100, int(parsed["score"])))
    except Exception:
        return 50


def score_job(job: dict) -> int:
    """Score a single job synchronously. Returns 50 on error."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return 50
    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": _build_user_message(job)}],
        )
        return _parse_score(response.content[0].text)
    except Exception:
        return 50


# ---------------------------------------------------------------------------
# Option 1 — Parallel async scoring
# ---------------------------------------------------------------------------

async def _score_job_async(client: anthropic.AsyncAnthropic, job: dict, semaphore: asyncio.Semaphore) -> int:
    async with semaphore:
        try:
            response = await client.messages.create(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": _build_user_message(job)}],
            )
            return _parse_score(response.content[0].text)
        except Exception:
            return 50


async def score_jobs_parallel(jobs: list[dict], concurrency: int = 20) -> list[int]:
    """Score a list of jobs in parallel. Returns scores in same order as input."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return [50] * len(jobs)

    client = anthropic.AsyncAnthropic(api_key=api_key)
    semaphore = asyncio.Semaphore(concurrency)
    tasks = [_score_job_async(client, job, semaphore) for job in jobs]
    scores = await asyncio.gather(*tasks)
    return list(scores)


# ---------------------------------------------------------------------------
# Option 2 — Anthropic Message Batches API (fire-and-forget, 50% cheaper)
# ---------------------------------------------------------------------------

def submit_batch(jobs: list[dict], job_ids: list[int]) -> str:
    """
    Submit all jobs as a single batch request.
    Returns the batch_id to poll later.
    job_ids are the DB pipeline IDs used as custom_id for mapping results back.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=api_key)

    requests = [
        {
            "custom_id": str(job_id),
            "params": {
                "model": _MODEL,
                "max_tokens": _MAX_TOKENS,
                "system": [{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                "messages": [{"role": "user", "content": _build_user_message(job)}],
            },
        }
        for job, job_id in zip(jobs, job_ids)
    ]

    batch = client.messages.batches.create(requests=requests)
    return batch.id


def poll_batch(batch_id: str) -> tuple[bool, dict[int, int]]:
    """
    Poll a batch for completion.
    Returns (is_done, {pipeline_id: score}).
    If not done yet, returns (False, {}).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=api_key)

    batch = client.messages.batches.retrieve(batch_id)

    if batch.processing_status != "ended":
        return False, {}

    results: dict[int, int] = {}
    for result in client.messages.batches.results(batch_id):
        pipeline_id = int(result.custom_id)
        if result.result.type == "succeeded":
            score = _parse_score(result.result.message.content[0].text)
        else:
            score = 50
        results[pipeline_id] = score

    return True, results
