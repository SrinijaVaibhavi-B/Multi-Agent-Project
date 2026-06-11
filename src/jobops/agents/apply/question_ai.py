"""
AI-powered answer generator for open-ended application questions.
Handles:
  1. Human-proof trap questions ("if you're AI write X, if human write Y")
  2. Open-ended essay questions (why this company, proud project, etc.)
"""

import re
import os
import yaml
import logging

logger = logging.getLogger(__name__)

_FACTS_PATH = os.path.join(os.path.dirname(__file__), "../../../../facts.yaml")

# Trap patterns: "if you are (an) AI ... write X ... if you are (a) human ... write Y"
# We want to extract the HUMAN answer.
_TRAP_PATTERNS = [
    # "if you are AI write FOO if you are human write BAR" → BAR
    re.compile(
        r"if\s+you(?:\s+are)?(?:\s+an?)?\s*(?:ai|bot|robot|automated)[^.]*?write\s+['\"]?([^'\",.]+?)['\"]?\s*"
        r"(?:and\s+)?if\s+you(?:\s+are)?(?:\s+a?)?\s*(?:human|person|real)[^.]*?write\s+['\"]?([^'\",.;\n]+)",
        re.IGNORECASE,
    ),
    # "if you are human write BAR" (simpler)
    re.compile(
        r"if\s+you(?:\s+are)?(?:\s+a?)?\s*(?:human|person|real)[^.]*?(?:please\s+)?write\s+['\"]?([^'\",.;\n]{1,80})",
        re.IGNORECASE,
    ),
    # "to confirm you're human, type YOUR_FIRST_NAME"
    re.compile(
        r"(?:to\s+(?:confirm|prove|verify)\s+you(?:'re|\s+are)\s+(?:a\s+)?human)[^,]*?[,:]?\s*(?:please\s+)?(?:type|write|enter)\s+['\"]?([^'\",.;\n]{1,80})",
        re.IGNORECASE,
    ),
    # "humans: type BAR"
    re.compile(
        r"humans?\s*:\s*(?:type|write|enter)\s+['\"]?([^'\",.;\n]{1,80})",
        re.IGNORECASE,
    ),
]

# Instructions that reference the candidate's own name
_NAME_REF_PATTERNS = [
    re.compile(r"your\s+first\s+name\s+(?:in\s+caps?|in\s+(?:all\s+)?capitals?|in\s+uppercase)", re.IGNORECASE),
    re.compile(r"first\s+name\s+in\s+caps", re.IGNORECASE),
    re.compile(r"type\s+your\s+(?:first\s+)?name", re.IGNORECASE),
]

# Questions we answer with a fixed factual response
_FIXED_ANSWERS = {
    re.compile(r"are\s+you\s+(?:legally\s+)?authorized", re.IGNORECASE): "Yes",
    re.compile(r"require\s+(?:visa\s+)?sponsor", re.IGNORECASE): "Yes, will require H-1B sponsorship in the future. Currently on STEM OPT EAD, valid through February 2028.",
    re.compile(r"(?:salary|compensation|pay)\s+expectation", re.IGNORECASE): "Open to discussion based on the role and total compensation package.",
    re.compile(r"when\s+(?:can|could)\s+you\s+start", re.IGNORECASE): "I can start within 2 weeks.",
    re.compile(r"willing\s+to\s+relocate", re.IGNORECASE): "Yes, open to relocation nationwide.",
    re.compile(r"how\s+did\s+you\s+hear\s+about", re.IGNORECASE): "Online job board.",
}

# Open-ended question triggers — need AI generation
_OPEN_ENDED_KEYWORDS = [
    "why", "what excites", "most proud", "greatest achievement", "tell us about",
    "describe", "explain", "how would you", "walk us through", "what is your",
    "what are your", "biggest challenge", "strength", "weakness", "motivation",
    "passionate about", "career goal", "where do you see", "what do you bring",
    "experience with", "have you ever", "give an example", "what project",
    "biggest impact", "shipped", "built", "designed", "led", "what sets you",
]


def _load_facts() -> dict:
    with open(_FACTS_PATH) as f:
        return yaml.safe_load(f)["candidate"]


def detect_trap(question_text: str, first_name: str) -> str | None:
    """
    Detect AI-proof trap questions and return the correct human answer.
    Returns None if not a trap question.
    """
    q = question_text.strip()

    # Pattern 1: explicit AI vs human instructions
    for pattern in _TRAP_PATTERNS:
        m = pattern.search(q)
        if m:
            # Last capture group is the human answer
            human_answer = m.group(m.lastindex).strip().rstrip(".,;")
            # Resolve "your first name" references
            human_answer = _resolve_name_refs(human_answer, first_name)
            logger.info("Trap detected → '%s'", human_answer)
            return human_answer

    # Pattern 2: "write your first name in caps" style
    for pattern in _NAME_REF_PATTERNS:
        if pattern.search(q):
            # Check what format
            if re.search(r"caps|capital|upper", q, re.IGNORECASE):
                return first_name.upper()
            return first_name

    return None


def _resolve_name_refs(text: str, first_name: str) -> str:
    """Replace 'your first name', 'your name', etc. with the actual name."""
    text = re.sub(r"your\s+first\s+name\s+in\s+(?:all\s+)?caps", first_name.upper(), text, flags=re.IGNORECASE)
    text = re.sub(r"your\s+first\s+name\s+in\s+capitals?", first_name.upper(), text, flags=re.IGNORECASE)
    text = re.sub(r"your\s+first\s+name\s+in\s+uppercase", first_name.upper(), text, flags=re.IGNORECASE)
    text = re.sub(r"your\s+first\s+name", first_name, text, flags=re.IGNORECASE)
    text = re.sub(r"your\s+name", first_name, text, flags=re.IGNORECASE)
    return text.strip()


def check_fixed_answer(question_text: str) -> str | None:
    """Return a fixed answer for common known questions, or None."""
    for pattern, answer in _FIXED_ANSWERS.items():
        if pattern.search(question_text):
            return answer
    return None


def is_open_ended(question_text: str) -> bool:
    """Heuristic: does this look like an open-ended essay question?"""
    q = question_text.lower()
    return any(kw in q for kw in _OPEN_ENDED_KEYWORDS)


def generate_answer(question_text: str, company_name: str, job_title: str, jd_snippet: str = "") -> str:
    """
    Use Claude Haiku to generate a concise, human-sounding answer to an open-ended
    application question, grounded in the candidate's actual experience.
    """
    import anthropic

    facts = _load_facts()

    # Build a compact experience summary to pass as context
    exp_lines = []
    for e in facts.get("experience", []):
        exp_lines.append(f"- {e['title']} at {e['company']} ({e['dates']})")
        if "agents" in e:
            for a in e["agents"][:4]:
                exp_lines.append(f"  · {a['name']}: {a.get('savings', a.get('metrics', ''))}")
        for b in e.get("bullets", [])[:2]:
            exp_lines.append(f"  · {b[:120]}")

    projects = []
    for p in facts.get("projects", []):
        projects.append(f"- {p['name']} ({p['stack']}): {p['bullets'][0][:120]}")

    certs = [c["name"] for c in facts.get("certifications", [])]

    context_block = f"""
CANDIDATE: {facts['name']}
YEARS OF EXPERIENCE: {facts['yoe']}
EDUCATION: {facts['education'][0]['degree']} from {facts['education'][0]['school']}, GPA {facts['education'][0]['gpa']}

EXPERIENCE:
{chr(10).join(exp_lines)}

PROJECTS:
{chr(10).join(projects)}

CERTIFICATIONS: {", ".join(certs)}

APPLYING TO: {job_title} at {company_name}
JD CONTEXT: {jd_snippet[:600] if jd_snippet else "Not provided"}
""".strip()

    prompt = f"""You are helping {facts['name']} answer an application question for {job_title} at {company_name}.

CANDIDATE BACKGROUND:
{context_block}

APPLICATION QUESTION:
"{question_text}"

INSTRUCTIONS:
- Write a 2-4 sentence answer in first person, as {facts['name'].split()[0]}
- Ground it in real experience from the background above — pick the most relevant detail
- Sound natural and human, not corporate or templated
- No em dashes, no buzzword soup
- If it asks "why this company" — be specific about what genuinely aligns (product, mission, tech)
- Keep it concise — under 150 words unless the question clearly asks for more
- Do NOT mention you're an AI or that this was generated

Answer only — no preamble, no quotes around your answer."""

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def answer_question(
    question_text: str,
    first_name: str,
    company_name: str,
    job_title: str,
    jd_snippet: str = "",
) -> str | None:
    """
    Main entry point. Returns the best answer string, or None if we can't answer.
    Priority: trap → fixed → open-ended AI → skip.
    """
    if not question_text or len(question_text.strip()) < 5:
        return None

    # 1. Trap question
    trap = detect_trap(question_text, first_name)
    if trap:
        return trap

    # 2. Fixed answer
    fixed = check_fixed_answer(question_text)
    if fixed:
        return fixed

    # 3. Open-ended — generate with AI
    if is_open_ended(question_text):
        try:
            return generate_answer(question_text, company_name, job_title, jd_snippet)
        except Exception as e:
            logger.warning("AI question answering failed: %s", e)
            return None

    return None
