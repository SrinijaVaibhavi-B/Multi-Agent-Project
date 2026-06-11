"""Rule-based job filtering — no LLM involved."""

from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Target role detection
# ---------------------------------------------------------------------------

_TARGET_KEYWORDS = [
    "software engineer",
    "swe",
    "software developer",
    "full stack",
    "fullstack",
    "frontend engineer",
    "front-end engineer",
    "backend engineer",
    "back-end engineer",
    "ai engineer",
    "applied ai",
    "ai software engineer",
    "full stack ai",
    "ml engineer",
    "platform engineer",
    "product engineer",
    "staff engineer",
    "senior engineer",
    "engineering manager",
]

_EXCLUDE_KEYWORDS = [
    "data scientist",
    "data analyst",
    "data engineer",
    "analytics engineer",
    "product manager",
    "program manager",
    "project manager",
    "ux designer",
    "ui designer",
    "product designer",
    "devrel",
    "developer advocate",
    "developer relations",
    "sales",
    "marketing",
    "recruiter",
    " hr ",
    "human resources",
    "research scientist",
    "research engineer",
    "qa engineer",
    "test engineer",
    "quality assurance",
    "consultant",
    "contractor",
]


def is_target_role(title: str) -> bool:
    """Return True if the job title matches a target engineering role."""
    lower = title.lower()

    # Hard excludes first
    for kw in _EXCLUDE_KEYWORDS:
        if kw in lower:
            # Special case: "Engineering Manager" is okay despite containing no exclude term
            # but "Product Manager" should be excluded
            return False

    # ML Engineer is only included if not research-focused
    if "ml engineer" in lower or "machine learning engineer" in lower:
        research_terms = ["research", "phd", "scientist"]
        if any(t in lower for t in research_terms):
            return False
        return True

    # Engineering Manager: allowed only when title explicitly contains that phrase
    if "manager" in lower:
        return "engineering manager" in lower

    # Check target keywords
    for kw in _TARGET_KEYWORDS:
        if kw in lower:
            return True

    return False


# ---------------------------------------------------------------------------
# Staffing firm detection
# ---------------------------------------------------------------------------

_STAFFING_KEYWORDS = [
    "staffing",
    "recruiting",
    "recruitment",
    "talent",
    "manpower",
    "consultancy",
    "outsourcing",
    "workforce",
    "personnel",
]

_STAFFING_COMBOS = [
    # "solutions" alone is too generic; require it with another signal
    ("solutions", "staffing"),
    ("solutions", "talent"),
    ("solutions", "recruiting"),
    ("agency", "staffing"),
    ("agency", "talent"),
    ("agency", "recruiting"),
]

_KNOWN_STAFFING_DOMAINS = {
    "kforce.com",
    "robertohalf.com",
    "adecco.com",
    "manpower.com",
    "heidrick.com",
    "infosys-bpo.com",
    "teksystems.com",
    "insight-global.com",
    "randstad.com",
    "toptal.com",
    "andela.com",
    "revature.com",
    "infosys.com",
    "wipro.com",
    "cognizant.com",
    "hcl.com",
}

# Job board aggregator accounts — not real employers
_KNOWN_JOB_BOARD_ORGS = {
    "chatgpt jobs",
    "ai jobs",
    "jobs via chatgpt",
    "jobgether",
    "jobleads",
    "jobrapido",
    "jooble",
    "resume-library",
    "jobsora",
    "jobs on the go",
    "zip recruiter",
    "jack & jill",
    "jack",
    "hunter bond",
    "remotehunter",
    "jobs via dice",
    "big wave digital",
    "jobgether",
    "jobright.ai",
    "jobright",
    "loop recruit",
    "omw consulting",
    "pavago",
    "differential.",
    "ness digital engineering",
}

# Companies explicitly blocklisted (spam posters, too large/competitive, defense, etc.)
_BLOCKLISTED_ORGS = {
    "speechify",         # spam — posts same job for 50+ cities
    "google",            # too large/competitive
    "alphabet",
    "dataannotation",    # data labeling, not real SWE
    "pragmatike",        # spam — same job posted dozens of times
    "hire feed",         # aggregator
    "fetchjobs.co",      # aggregator
    "revature",          # training bootcamp + staffing, not real SWE employer
}

# Pure defense-only companies — no normal SWE roles worth applying to
_DEFENSE_ORGS = {
    "lockheed martin",
    "lockheedmartin",
    "booz allen",
    "booz allen hamilton",
    "northrop grumman",
    "northrop",
    "l3harris",
    "l3 technologies",
    "saic",
    "leidos",
    "amentum",
    "peraton",
    "caci",
    "rtx",
    "raytheon",
    "collins aerospace",
    "pratt & whitney",
    "general dynamics",
    "bae systems",
    "mitre corporation",
}

# Job title/description keywords that indicate citizenship or clearance requirements
# Applied to ALL companies — catches Boeing, GM etc. roles that require clearance
_CLEARANCE_KEYWORDS = [
    "top secret",
    "ts/sci",
    "secret clearance",
    "security clearance",
    "clearance required",
    "clearance eligible",
    "dod clearance",
    "itar",
    "us citizenship required",
    "u.s. citizenship required",
    "must be a us citizen",
    "must be a u.s. citizen",
    "active clearance",
    "public trust clearance",
]


def is_staffing_firm(organization: str, source_domain: str) -> bool:
    """Return True if the company looks like a staffing/recruiting firm or job board aggregator."""
    if source_domain in _KNOWN_STAFFING_DOMAINS:
        return True

    org_lower = organization.lower()

    if org_lower in _KNOWN_JOB_BOARD_ORGS:
        return True

    if org_lower in _BLOCKLISTED_ORGS:
        return True

    for kw in _STAFFING_KEYWORDS:
        if kw in org_lower:
            return True

    for kw1, kw2 in _STAFFING_COMBOS:
        if kw1 in org_lower and kw2 in org_lower:
            return True

    return False


# ---------------------------------------------------------------------------
# Ghost job scoring
# ---------------------------------------------------------------------------

def compute_ghost_score(job: dict) -> int:
    """Return 0-100 ghost likelihood score. Higher = more likely ghost."""
    score = 0

    # Age of posting
    date_posted_raw = job.get("date_posted") or job.get("date_created")
    if date_posted_raw:
        try:
            if isinstance(date_posted_raw, str):
                # Strip trailing Z or timezone info for naive parse
                date_str = date_posted_raw.replace("Z", "").split("+")[0]
                posted_dt = datetime.fromisoformat(date_str)
            else:
                posted_dt = date_posted_raw

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            days_old = (now - posted_dt).days
            if days_old > 30:
                score += 40
            elif days_old > 14:
                score += 20
        except (ValueError, TypeError):
            pass

    # Short description
    desc = job.get("description_text", "") or ""
    if len(desc) < 200:
        score += 25

    # Extremely generic title
    title = (job.get("title", "") or "").strip()
    if len(title) < 20 and title.lower() in (
        "software engineer",
        "engineer",
        "developer",
        "software developer",
    ):
        score += 10

    # No visa + no salary
    visa = job.get("ai_visa_sponsorship")
    salary_min = job.get("ai_salary_min_value")
    salary_max = job.get("ai_salary_max_value")
    if visa is False and not salary_min and not salary_max:
        score += 5

    return min(score, 100)


# ---------------------------------------------------------------------------
# Master filter
# ---------------------------------------------------------------------------

def is_defense_role(organization: str, title: str) -> bool:
    """Return True if job is defense/government contractor or requires clearance."""
    org_lower = organization.lower()
    # Exact match or substring match for defense orgs
    if any(d in org_lower for d in _DEFENSE_ORGS):
        return True
    title_lower = title.lower()
    return any(kw in title_lower for kw in _CLEARANCE_KEYWORDS)


def should_include(job: dict) -> tuple[bool, str]:
    """Master filter. Returns (include, reason)."""
    title = job.get("title", "") or ""
    org = job.get("organization", "") or ""
    domain = job.get("source_domain", "") or ""

    if not is_target_role(title):
        return False, "role_mismatch"

    if is_staffing_firm(org, domain):
        return False, "staffing_firm"

    if is_defense_role(org, title):
        return False, "defense_blocked"

    ghost = compute_ghost_score(job)
    if ghost > 70:
        return False, "likely_ghost"

    return True, "ok"
