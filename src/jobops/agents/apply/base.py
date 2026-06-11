"""Base applier — shared utilities for all ATS fillers."""

import os
import time
from dataclasses import dataclass
from typing import Literal

import yaml
from playwright.sync_api import Page

_FACTS_PATH = os.path.join(os.path.dirname(__file__), "../../../../facts.yaml")

ApplyResult = Literal["applied", "review_needed", "failed"]

# Standard answers for common form questions
_WORK_AUTH_ANSWERS = {
    "are you legally authorized": "Yes",
    "authorized to work in the united states": "Yes",
    "authorized to work in the us": "Yes",
    "work authorization": "Yes",
    "legally eligible": "Yes",
}

_VISA_ANSWERS = {
    "require sponsorship": "Yes",
    "need sponsorship": "Yes",
    "visa sponsorship": "Yes",
    "will you now or in the future require": "Yes",
    "require visa": "Yes",
}

_SALARY_KEYWORDS = ["salary", "compensation", "pay", "expected", "desired"]

_SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")


@dataclass
class CandidateProfile:
    first_name: str
    last_name: str
    email: str
    phone: str
    linkedin: str
    github: str
    location: str = "United States"
    work_authorization: str = "Yes"
    requires_sponsorship: str = "Yes"


def load_profile() -> CandidateProfile:
    with open(_FACTS_PATH) as f:
        c = yaml.safe_load(f)["candidate"]
    name_parts = c["name"].split()
    return CandidateProfile(
        first_name=name_parts[0],
        last_name=" ".join(name_parts[1:]),
        email=c["email"],
        phone=c["phone"],
        linkedin=c["linkedin"],
        github=c["github"],
    )


def take_screenshot(page: Page, name: str) -> str:
    os.makedirs(_SCREENSHOT_DIR, exist_ok=True)
    path = os.path.join(_SCREENSHOT_DIR, f"{name}_{int(time.time())}.png")
    page.screenshot(path=path, full_page=True)
    return path


def safe_fill(page: Page, selector: str, value: str, timeout: int = 3000) -> bool:
    """Fill a field if it exists. Returns True if filled."""
    try:
        el = page.wait_for_selector(selector, timeout=timeout, state="visible")
        if el:
            el.fill(value)
            return True
    except Exception:
        pass
    return False


def safe_select(page: Page, selector: str, value: str, timeout: int = 3000) -> bool:
    """Select dropdown option by label or value."""
    try:
        el = page.wait_for_selector(selector, timeout=timeout, state="visible")
        if el:
            try:
                el.select_option(label=value)
            except Exception:
                el.select_option(value=value)
            return True
    except Exception:
        pass
    return False


def detect_captcha(page: Page) -> bool:
    content = page.content().lower()
    return any(x in content for x in ["captcha", "recaptcha", "cf-challenge", "hcaptcha", "i am not a robot"])


def detect_unexpected_fields(page: Page) -> list[str]:
    """Return list of unusual field labels found on the page."""
    unexpected = []
    content = page.content().lower()
    flags = [
        "cover letter", "essay", "writing sample", "video",
        "salary expectation", "desired salary", "expected salary",
    ]
    for flag in flags:
        if flag in content:
            unexpected.append(flag)
    return unexpected
