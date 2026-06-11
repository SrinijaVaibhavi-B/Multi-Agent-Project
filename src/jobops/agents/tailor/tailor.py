"""LLM-based resume tailoring — produces a structured resume dict from facts + JD."""

import json
import os
import re

import anthropic
import yaml

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 4096
_FACTS_PATH = os.path.join(os.path.dirname(__file__), "../../../../facts.yaml")

_SYSTEM_PROMPT = """You are an expert resume tailor. Given a candidate's full profile (facts) and a job description, you produce a tailored resume JSON.

Rules — strictly enforced:
1. NEVER invent, exaggerate, or add any experience, skill, metric, or claim not present in the facts.
2. You MAY reorder bullets, emphasize relevant ones, and reword for clarity — but every claim must be traceable to the facts.
3. Select the 3-5 most relevant bullets per job. Drop less relevant ones to keep the resume tight.
4. Write a tailored 2-3 sentence summary that connects the candidate's actual background to THIS specific role.
5. Reorder the skills sections to put the most relevant technologies first.
6. Keep projects only if relevant to the role — omit if not.
7. Output ONLY valid JSON. No markdown fences, no explanation.

Output schema:
{
  "summary": "2-3 sentence tailored summary",
  "skills": {
    "Languages": ["Python", ...],
    "Frontend": [...],
    "Backend & APIs": [...],
    "Databases": [...],
    "AI & Agentic Systems": [...],
    "Cloud & Infrastructure": [...],
    "Testing & QA": [...],
    "Observability & MLOps": [...]
  },
  "experience": [
    {
      "company": "...",
      "title": "...",
      "location": "...",
      "dates": "...",
      "contract_notes": "...",
      "bullets": ["bullet 1", "bullet 2", ...]
    }
  ],
  "volunteer": [
    {
      "org": "...",
      "title": "...",
      "location": "...",
      "dates": "...",
      "bullets": [...]
    }
  ],
  "projects": [
    {
      "name": "...",
      "stack": "...",
      "bullets": [...]
    }
  ],
  "include_volunteer": true,
  "include_projects": true
}"""


def _load_facts() -> dict:
    with open(_FACTS_PATH) as f:
        return yaml.safe_load(f)


def _build_prompt(facts: dict, job: dict) -> str:
    c = facts["candidate"]
    facts_str = json.dumps({
        "name": c["name"],
        "summary": c["summary"],
        "skills": c["skills"],
        "experience": c["experience"],
        "volunteer": c.get("volunteer", []),
        "projects": c.get("projects", []),
        "certifications": c.get("certifications", []),
        "education": c["education"],
    }, indent=2)

    jd = (job.get("raw_description") or "")[:3000]
    return f"""CANDIDATE FACTS (source of truth — do not add anything beyond this):
{facts_str}

JOB TO TAILOR FOR:
Title: {job.get("job_title", "")}
Company: {job.get("company_name", "")}

Job Description:
{jd}

Produce the tailored resume JSON now."""


def tailor_resume(job: dict) -> dict | None:
    """Tailor resume for a single job. Returns structured dict or None on error."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    facts = _load_facts()
    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": _build_prompt(facts, job)}],
        )
        text = response.content[0].text.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = re.sub(r"^```[a-z]*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        return json.loads(text)
    except Exception as e:
        print(f"[tailor] LLM error: {e}")
        return None


def verify_resume(tailored: dict, facts: dict) -> tuple[bool, list[str]]:
    """
    Verifier pass: check that key metrics in tailored resume exist in facts.
    Returns (passed, list_of_issues).
    """
    issues = []
    facts_str = json.dumps(facts).lower()

    # Extract all bullet text
    all_bullets = []
    for job in tailored.get("experience", []):
        all_bullets.extend(job.get("bullets", []))
    for v in tailored.get("volunteer", []):
        all_bullets.extend(v.get("bullets", []))
    for p in tailored.get("projects", []):
        all_bullets.extend(p.get("bullets", []))

    # Check for suspicious numbers/claims not in facts
    import re
    # Build a version of facts_str with commas stripped for number matching
    facts_str_ncomma = facts_str.replace(",", "")
    for bullet in all_bullets:
        numbers = re.findall(r'\b\d[\d,]*\+?\b', bullet)
        for num in numbers:
            clean = num.replace(",", "").replace("+", "")
            # Check both comma and no-comma versions
            if clean not in facts_str_ncomma and num not in facts_str and len(clean) > 3:
                issues.append(f"Unverifiable number '{num}' in: {bullet[:80]}")

    return len(issues) == 0, issues
