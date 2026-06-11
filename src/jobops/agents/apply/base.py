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


# Selectors we already handle explicitly — skip these in open question scan
_KNOWN_FIELD_SELECTORS = {
    "input[name='name']", "input[name='_systemfield_name']",
    "input#first_name", "input#last_name",
    "input[name='email']", "input#email", "input[name='_systemfield_email']",
    "input[name='phone']", "input#phone", "input[name='_systemfield_phone']",
    "input[name*='linkedin']", "input[id*='linkedin']",
    "input[name*='github']", "input[id*='github']",
    "input[name*='website']", "input[name='location']",
    "input#job_application_location", "input[name='org']",
    "input[name='urls[LinkedIn]']", "input[name='urls[GitHub]']",
    "input[name='urls[Portfolio]']",
}


def fill_open_questions(
    page: Page,
    profile: "CandidateProfile",
    company_name: str,
    job_title: str,
    jd_snippet: str = "",
) -> None:
    """
    Find all textarea and text inputs not already filled, get their label text,
    and use question_ai to fill trap questions and open-ended essay questions.
    """
    from jobops.agents.apply.question_ai import answer_question

    # Gather all textareas + visible text inputs
    elements = []
    try:
        elements += page.query_selector_all("textarea")
        elements += page.query_selector_all("input[type='text']:not([type='hidden'])")
    except Exception:
        return

    for el in elements:
        try:
            # Skip if already filled
            current_val = el.input_value() if el.get_attribute("type") != "textarea" else el.text_content()
            if current_val and current_val.strip():
                continue

            # Get label text for this element
            label_text = _get_label_for(page, el)
            if not label_text or len(label_text.strip()) < 4:
                continue

            # Skip known standard fields
            tag = el.evaluate("el => el.tagName").lower()
            name = el.get_attribute("name") or ""
            el_id = el.get_attribute("id") or ""
            if any(kw in name.lower() or kw in el_id.lower() for kw in [
                "name", "email", "phone", "linkedin", "github", "website", "location", "org", "url"
            ]):
                continue

            answer = answer_question(
                question_text=label_text,
                first_name=profile.first_name,
                company_name=company_name,
                job_title=job_title,
                jd_snippet=jd_snippet,
            )
            if answer:
                el.fill(answer)
                page.wait_for_timeout(300)

        except Exception:
            continue


def _get_label_for(page: Page, el) -> str:
    """Extract label text for a form element."""
    try:
        return page.evaluate("""el => {
            // Explicit label[for=id]
            if (el.id) {
                const lbl = document.querySelector(`label[for='${el.id}']`);
                if (lbl) return lbl.innerText || lbl.textContent || '';
            }
            // Wrapping label
            const wrap = el.closest('label');
            if (wrap) return wrap.innerText || wrap.textContent || '';
            // Sibling label or parent question container
            const parent = el.parentElement;
            if (parent) {
                const lbl = parent.querySelector('label') || parent.previousElementSibling;
                if (lbl) return lbl.innerText || lbl.textContent || '';
            }
            // aria-label / placeholder as last resort
            return el.getAttribute('aria-label') || el.getAttribute('placeholder') || '';
        }""", el).strip()
    except Exception:
        return ""
