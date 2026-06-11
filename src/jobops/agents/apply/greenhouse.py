"""Greenhouse ATS form filler."""

from playwright.sync_api import Page

from jobops.agents.apply.base import (
    ApplyResult, CandidateProfile,
    safe_fill, safe_select, take_screenshot,
    detect_captcha, detect_unexpected_fields,
    fill_open_questions,
)


def apply_greenhouse(page: Page, job_url: str, resume_path: str, profile: CandidateProfile, jd_snippet: str = "") -> tuple[ApplyResult, str]:
    """
    Fill and submit a Greenhouse application.
    Returns (result, reason/screenshot_path).
    """
    try:
        # Navigate — handle both direct job URL and board URL
        page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        # Check for captcha early
        if detect_captcha(page):
            ss = take_screenshot(page, "greenhouse_captcha")
            return "review_needed", ss

        # Unexpected fields check
        unexpected = detect_unexpected_fields(page)
        if unexpected:
            ss = take_screenshot(page, "greenhouse_unexpected")
            return "review_needed", f"Unexpected fields: {unexpected} — {ss}"

        # --- Personal info ---
        safe_fill(page, "input#first_name", profile.first_name)
        safe_fill(page, "input#last_name", profile.last_name)
        safe_fill(page, "input#email", profile.email)
        safe_fill(page, "input#phone", profile.phone)

        # Location (city)
        safe_fill(page, "input#job_application_location", "United States")

        # LinkedIn
        safe_fill(page, "input[name*='linkedin']", profile.linkedin)
        safe_fill(page, "input[id*='linkedin']", profile.linkedin)

        # GitHub / website
        safe_fill(page, "input[name*='github']", profile.github)
        safe_fill(page, "input[id*='github']", profile.github)
        safe_fill(page, "input[name*='website']", profile.github)

        # --- Resume upload ---
        resume_input = page.query_selector("input[type='file']")
        if resume_input:
            resume_input.set_input_files(resume_path)
            page.wait_for_timeout(1500)
        else:
            ss = take_screenshot(page, "greenhouse_no_resume_input")
            return "review_needed", f"No file input found — {ss}"

        # --- Work authorization dropdowns ---
        _handle_work_auth(page, profile)

        # --- Open-ended / trap questions ---
        company_name = job_url.split("/")[2] if job_url else "the company"
        fill_open_questions(page, profile, company_name, "", jd_snippet)

        # --- Submit ---
        submit = page.query_selector("input[type='submit'], button[type='submit']")
        if not submit:
            ss = take_screenshot(page, "greenhouse_no_submit")
            return "review_needed", f"No submit button — {ss}"

        submit.click()
        page.wait_for_timeout(3000)

        # Verify success
        content = page.content().lower()
        if any(x in content for x in ["thank you", "application received", "successfully submitted", "application submitted"]):
            return "applied", "success"

        # Check for errors
        if any(x in content for x in ["error", "required", "please fill"]):
            ss = take_screenshot(page, "greenhouse_error")
            return "review_needed", f"Form error after submit — {ss}"

        # Ambiguous — take screenshot for review
        ss = take_screenshot(page, "greenhouse_ambiguous")
        return "review_needed", f"Unclear outcome — {ss}"

    except Exception as e:
        try:
            ss = take_screenshot(page, "greenhouse_exception")
        except Exception:
            ss = "no screenshot"
        return "failed", f"{e} — {ss}"


def _handle_work_auth(page: Page, profile: CandidateProfile) -> None:
    """Handle work authorization and visa sponsorship questions."""
    # Try common select patterns
    for sel in [
        "select[name*='work_auth']", "select[id*='work_auth']",
        "select[name*='authorization']", "select[id*='authorization']",
    ]:
        safe_select(page, sel, "Yes", timeout=1000)

    for sel in [
        "select[name*='sponsor']", "select[id*='sponsor']",
        "select[name*='visa']", "select[id*='visa']",
    ]:
        safe_select(page, sel, "Yes", timeout=1000)

    # Handle radio buttons — look for yes/no pairs
    try:
        radios = page.query_selector_all("input[type='radio']")
        for radio in radios:
            label = page.evaluate("el => el.closest('label')?.textContent || ''", radio).strip().lower()
            val = (radio.get_attribute("value") or "").lower()
            if val in ("yes", "true", "1") and any(
                kw in label for kw in ["authoriz", "eligible", "legally", "sponsor", "visa"]
            ):
                radio.click()
    except Exception:
        pass
