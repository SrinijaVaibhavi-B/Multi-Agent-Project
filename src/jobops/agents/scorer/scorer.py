"""LLM-based fit scoring for jobs that pass the rule-based pre-filter."""

import json
import os

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


def score_job(job: dict) -> int:
    """
    Score a job using Claude for fit against the candidate profile.

    Returns an integer fit score from 0 to 100.
    Returns 50 on any error (neutral score to avoid false rejections).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        # No API key — return neutral score
        return 50

    client = anthropic.Anthropic(api_key=api_key)

    title = job.get("job_title") or "Unknown Title"
    company = job.get("company_name") or "Unknown Company"
    description = job.get("raw_description") or ""
    if len(description) > _DESCRIPTION_TRUNCATE:
        description = description[:_DESCRIPTION_TRUNCATE] + "... [truncated]"

    user_message = f"""Job Title: {title}
Company: {company}

Job Description:
{description}

Evaluate this job's fit for the candidate and return a JSON score."""

    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {"role": "user", "content": user_message},
            ],
        )

        raw_text = response.content[0].text.strip()

        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()

        parsed = json.loads(raw_text)
        score = int(parsed["score"])
        score = max(0, min(100, score))
        return score

    except (json.JSONDecodeError, KeyError, ValueError, IndexError):
        return 50
    except Exception:
        return 50
