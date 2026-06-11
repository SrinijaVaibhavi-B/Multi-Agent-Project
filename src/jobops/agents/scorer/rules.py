"""Pure rule-based pre-filter — no LLM. Fast, cheap, runs first."""

import re


# YOE levels accepted (from API field ai_experience_level)
_ACCEPTED_YOE = {None, "0-1", "1-2", "2-5"}
_REJECTED_YOE = {"5-10", "10+"}


def check_yoe(job: dict) -> tuple[bool, str]:
    """
    Check years-of-experience level from job dict.

    Uses the `ai_experience_level` field from the API.
    Accepts: None (unknown), "0-1", "1-2", "2-5"
    Rejects: "5-10", "10+"
    """
    level = job.get("ai_experience_level")
    if level in _REJECTED_YOE:
        return False, f"yoe_too_senior: requires {level} years experience"
    return True, "ok"


# Hard-exclude keyword patterns for domain exclusions.
# These target DESIGNING chips/hardware, not USING them.
_DOMAIN_EXCLUSION_PATTERNS = [
    r"\brobotic(?:s)?\b",
    r"\bembedded\b",
    r"\bfirmware\b",
    # GPU designing/architecture (not using)
    r"\bgpu\s+(?:architect(?:ure)?|design|engineer(?:ing)?|program(?:ming)?)\b",
    r"\bgpu\s+arch\b",
    # TPU
    r"\btpu\b",
    # FPGA / ASIC / chip design
    r"\bfpga\b",
    r"\basic\b",
    r"\bchip\s+design\b",
    r"\bsilicon\s+design\b",
    r"\bsilicon\s+engineer\b",
    # Semiconductor
    r"\bsemiconductor\b",
    # Kernel / device drivers
    r"\bkernel\s+driver\b",
    r"\bdevice\s+driver\b",
    # Real-time OS
    r"\breal[- ]time\s+os\b",
    r"\brtos\b",
    # Avionics
    r"\bavionics\b",
    # DSP / signal processing engineering roles
    r"\bdsp\s+engineer\b",
    r"\bsignal\s+processing\s+engineer\b",
    # HDL languages (dead giveaway of hardware role)
    r"\bverilog\b",
    r"\bvhdl\b",
    # Circuit / PCB design
    r"\bcircuit\s+design\b",
    r"\bpcb\b",
    # Hardware engineer (but NOT "software hardware" or "software-defined hardware")
    r"(?<!software\s)\bhardware\s+engineer\b",
    r"(?<!software[-\s])\bhardware\s+engineer\b",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _DOMAIN_EXCLUSION_PATTERNS]


def check_domain_exclusions(title: str, description: str) -> tuple[bool, str]:
    """
    Hard-exclude jobs in hardware/embedded/chip domains.

    Checks both title and description for exclusion keywords.
    Targets jobs designing chips/hardware — not jobs that merely use GPUs.
    """
    combined_text = f"{title or ''} {description or ''}"
    for pattern in _COMPILED_PATTERNS:
        match = pattern.search(combined_text)
        if match:
            return False, f"domain_excluded: matched '{match.group()}'"
    return True, "ok"


def apply_rules(job: dict) -> tuple[bool, str]:
    """
    Run all rule-based checks on a job dict.

    Returns (pass, reason). reason="ok" if all checks pass,
    otherwise returns the first failure reason.
    """
    yoe_pass, yoe_reason = check_yoe(job)
    if not yoe_pass:
        return False, yoe_reason

    title = job.get("job_title") or ""
    description = job.get("raw_description") or ""
    domain_pass, domain_reason = check_domain_exclusions(title, description)
    if not domain_pass:
        return False, domain_reason

    return True, "ok"
