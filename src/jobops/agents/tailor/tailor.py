"""LLM-based resume tailoring — produces a structured resume dict from facts + JD."""

import json
import os
import re

import anthropic
import yaml

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 4096
_FACTS_PATH = os.path.join(os.path.dirname(__file__), "../../../../facts.yaml")

_SYSTEM_PROMPT = """You are an expert resume writer and career strategist specializing in AI engineering, full-stack development, and forward-deployed engineering roles. Your job is to take the candidate's master experience data and a provided job description (JD), and produce a perfectly tailored, 1-page resume that passes ATS screening and impresses human reviewers.
You write like a professional resume writer who understands psychology, persuasion, and what recruiters actually look for in 2026. You never sound like AI wrote it. You never use filler language. Every word earns its place.

FORMATTING RULES
- NO em dashes anywhere. Use commas, periods, or restructure the sentence.
- No tech stack in the Professional Summary — summary is about impact, scope, and identity only
- Bold key metrics, numbers, company names, and tech stack terms inline within bullets using <strong> tags
- No newsletter-style bold headings within bullet text
- No excessive bolding — only bold what truly matters
- 1 page maximum. Be ruthless.
- Clean, readable formatting

PROFESSIONAL SUMMARY RULES
- 4-5 lines, paragraph format (not bullets)
- Start with role identity and value proposition
- Must cover: who you are, credentials + track record with numbers, scope of work (full stack + AI), approach/methodology
- Include AI dev tooling mention (Claude Code, GitHub Copilot, Cursor)
- Include agile mention
- Bold key words and metrics using <strong> tags
- No em dashes
- Human voice — not AI-sounding
- No filler words: no "passionate", "dedicated", "hard-working", "team player"

BULLET WRITING RULES — MOST IMPORTANT
- Result first → business problem → how you solved it → tech stack bolded with <strong> tags
- Every bullet must connect action to quantifiable outcome
- No vague statements — every claim must be specific
- No em dashes
- Max 2 lines per bullet
- Tech stack bolded inline using <strong> tags (not listed separately)
- No AI-sounding language
- Bullets must read like a human wrote them — vary sentence rhythm and length
- Lead verbs: Saved, Built, Eliminated, Achieved, Hardened, Owned, Delivered, Maintained, Architected, Reduced, Prevented, Drove, Secured, Closed

SKILLS SECTION RULES
- Grouped by category, reordered with most JD-relevant category first
- Categories: Technologies, Frontend, Backend & APIs, Databases & Vector Stores, AI & Agentic Systems, Cloud & Infrastructure, Microsoft Ecosystem, Testing & QA, Observability & MLOps
- No redundancy across categories

TAILORING RULES
- Read the JD carefully and identify: required skills, preferred skills, key verbs used, domain context
- Mirror the JD's language where it matches real experience — do not invent experience
- Reorder bullet points within each role to lead with most JD-relevant work
- Select the 2-3 most relevant projects from the master data
- Adjust summary to reflect the specific role type (AI Engineer vs FDE vs Full Stack vs Solutions Architect)
- If JD mentions specific tools candidate has used, surface them in both skills AND bullets
- For FDE/customer-facing roles: emphasize stakeholder work, AI board presentations, requirements gathering
- For pure engineering roles: emphasize technical depth, architecture, eval pipelines, system design
- For startup/founding engineer roles: emphasize sole ownership, self-initiated projects, end-to-end delivery
- Mirror the JD's exact language for responsibilities where possible (ATS matching)

WHAT TO NEVER DO
- Never use em dashes
- Never put tech stack in summary
- Never use: passionate, dedicated, hard-working, team player, detail-oriented, results-driven
- Never start every bullet with the same verb
- Never exceed 1 page worth of content
- Never sound like AI wrote it

STRICT INTEGRITY RULES
- NEVER invent experience, metrics, or tech not in the facts
- Every claim must be traceable to the master experience data provided

OUTPUT — return ONLY valid JSON, no markdown fences, no explanation:
{
  "summary": "<strong>bold key words</strong> in paragraph text, 4-5 lines, no tech stack",
  "skills": {
    "Technologies": ["Python", "TypeScript", ...],
    "Frontend": [...],
    "Backend & APIs": [...],
    "Databases & Vector Stores": [...],
    "AI & Agentic Systems": [...],
    "Cloud & Infrastructure": [...],
    "Microsoft Ecosystem": [...],
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
      "bullets": ["Result with <strong>metric</strong> by doing X using <strong>Tech, Tech</strong> for context.", ...]
    }
  ],
  "volunteer": [{"org": "...", "title": "...", "location": "...", "dates": "...", "bullets": [...]}],
  "projects": [{"name": "...", "stack": "...", "bullets": [...]}],
  "include_volunteer": true,
  "include_projects": true
}"""


def _load_facts() -> dict:
    with open(_FACTS_PATH) as f:
        return yaml.safe_load(f)


def _build_prompt(facts: dict, job: dict) -> str:
    c = facts["candidate"]

    # Build rich master data string
    master = {
        "candidate_identity": {
            "name": c["name"],
            "email": c["email"],
            "phone": c["phone"],
            "github": c["github"],
            "linkedin": c["linkedin"],
            "work_authorization": c.get("work_authorization", ""),
        },
        "skills": c["skills"],
        "experience": c["experience"],
        "volunteer": c.get("volunteer", []),
        "education": c["education"],
        "projects": c.get("projects", []),
        "certifications": c.get("certifications", []),
    }

    jd = (job.get("raw_description") or "")[:3500]
    return f"""MASTER EXPERIENCE DATA (source of truth — never add anything beyond this):
{json.dumps(master, indent=2)}

JOB TO TAILOR FOR:
Title: {job.get("job_title", "")}
Company: {job.get("company_name", "")}

Job Description:
{jd}

Before writing:
1. Identify the top 5 skills/experiences the JD screens for
2. Map those to the candidate's real experience
3. Write summary to speak directly to this role type
4. Select and reorder bullets to lead with most relevant work
5. Ensure every required JD skill appears in the resume if candidate genuinely has it

Output the tailored resume JSON now. 1 page maximum."""


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
        if text.startswith("```"):
            text = re.sub(r"^```[a-z]*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        result = json.loads(text)
        return _clean_em_dashes(result)
    except Exception as e:
        print(f"[tailor] LLM error: {e}")
        return None


def _clean_em_dashes(obj):
    """Recursively strip em/en dashes throughout the resume dict."""
    if isinstance(obj, str):
        return obj.replace("—", ",").replace("–", "-")
    if isinstance(obj, list):
        return [_clean_em_dashes(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _clean_em_dashes(v) for k, v in obj.items()}
    return obj


def verify_resume(tailored: dict, facts: dict) -> tuple[bool, list[str]]:
    """Verifier pass: check key metrics in tailored resume trace to facts."""
    issues = []
    facts_str = json.dumps(facts).lower()
    facts_str_ncomma = facts_str.replace(",", "")

    all_bullets = []
    for job in tailored.get("experience", []):
        all_bullets.extend(job.get("bullets", []))
    for v in tailored.get("volunteer", []):
        all_bullets.extend(v.get("bullets", []))
    for p in tailored.get("projects", []):
        all_bullets.extend(p.get("bullets", []))

    for bullet in all_bullets:
        # Strip HTML tags before checking numbers
        plain = re.sub(r"<[^>]+>", "", bullet)
        numbers = re.findall(r'\b\d[\d,]*\+?\b', plain)
        for num in numbers:
            clean = num.replace(",", "").replace("+", "")
            if clean not in facts_str_ncomma and num not in facts_str and len(clean) > 3:
                issues.append(f"Unverifiable number '{num}' in: {plain[:80]}")

    return len(issues) == 0, issues
