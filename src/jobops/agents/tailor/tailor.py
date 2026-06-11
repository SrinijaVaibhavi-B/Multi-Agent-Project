"""LLM-based resume tailoring — produces a structured resume dict from facts + JD."""

import json
import os
import re

import anthropic
import yaml

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 4096
_FACTS_PATH = os.path.join(os.path.dirname(__file__), "../../../../facts.yaml")

_SYSTEM_PROMPT = """You are an expert resume tailor. Given a candidate's full profile (facts) and a job description, produce a tailored resume JSON.

BULLET FORMAT — every bullet MUST follow this exact structure:
  <strong>[Result/metric]</strong> by [action verb + what you did] using <strong>[Tech1, Tech2, Tech3]</strong> [for/across/enabling] [context or impact].

Rules for bullets:
- START with the achievement or metric in <strong> tags: e.g. <strong>Saved $98,800+ annually</strong> or <strong>Cut detection time from hours to minutes</strong>
- PUT tech stack in the MIDDLE, always in <strong> tags: e.g. using <strong>LangGraph, Azure OpenAI, FastAPI</strong>
- END with context/scale/reason: e.g. "across 6,000+ enterprise users" or "eliminating 15,000+ manual hours annually"
- Bold ALL metrics (numbers, percentages, dollar amounts, counts) with <strong> tags
- Select 3-4 most relevant bullets per role — drop the rest to save space
- If a bullet doesn't have a clear metric, START with a strong action verb in <strong>tags</strong>

STACK MATCHING — critical:
- If the JD lists a tech as REQUIRED or strongly preferred (e.g. .NET, C#, Go, C++, Java, Node.js, Rails), you MUST:
  a) Rewrite existing bullets to mention that tech where plausible (e.g. "Java/Spring Boot" → highlight Java more)
  b) Reorder skills to put that tech first in its category
  c) If the candidate genuinely used it (check facts), surface it prominently

STRICT RULES:
1. NEVER invent experience, metrics, or tech not in the facts
2. Reword and reorder freely — every claim must trace back to facts
3. Write a 2-sentence tailored summary connecting candidate's background to THIS role
4. Keep the resume to 1-2 pages — be ruthless about cutting weak bullets
5. Include volunteer section only if it adds relevant signal for this role
6. Output ONLY valid JSON — no markdown, no explanation
7. NEVER use em dashes (—) anywhere. Use commas, periods, or rephrase instead
8. LANGUAGE TONE — write 10-15% human: slightly natural, not robotic corporate-speak.
   Good: "helped cut fraud losses by $2M+" or "built the monitoring system that caught failures in minutes"
   Bad: "Spearheaded the implementation of a robust real-time monitoring solution"
   Keep it confident and direct, like a sharp engineer wrote it, not a resume template

Output schema:
{
  "summary": "2 sentence tailored summary",
  "skills": {
    "Languages": ["Python", ...],
    "Frontend": [...],
    "Backend & APIs": [...],
    "Databases": [...],
    "AI & Agentic Systems": [...],
    "Cloud & Infra": [...],
    "Testing & QA": [...],
    "Observability": [...]
  },
  "experience": [
    {
      "company": "...",
      "title": "...",
      "location": "...",
      "dates": "...",
      "contract_notes": "...",
      "bullets": ["<strong>Result</strong> by action using <strong>Tech</strong> for context.", ...]
    }
  ],
  "volunteer": [...],
  "projects": [...],
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
        result = json.loads(text)
        return _clean_em_dashes(result)
    except Exception as e:
        print(f"[tailor] LLM error: {e}")
        return None


def _clean_em_dashes(obj):
    """Recursively replace em dashes with commas throughout the resume dict."""
    if isinstance(obj, str):
        return obj.replace("—", ",").replace("–", "-")
    if isinstance(obj, list):
        return [_clean_em_dashes(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _clean_em_dashes(v) for k, v in obj.items()}
    return obj


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
