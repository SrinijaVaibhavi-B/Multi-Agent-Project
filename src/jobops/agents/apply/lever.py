"""Lever ATS form filler."""

from playwright.sync_api import Page

from jobops.agents.apply.base import (
    ApplyResult, CandidateProfile,
    safe_fill, take_screenshot,
    detect_captcha, detect_unexpected_fields,
    fill_open_questions,
)


def apply_lever(page: Page, job_url: str, resume_path: str, profile: CandidateProfile, jd_snippet: str = "") -> tuple[ApplyResult, str]:
    """
    Fill and submit a Lever application.
    Returns (result, reason/screenshot_path).
    """
    try:
        # Lever apply page is usually /apply appended
        apply_url = job_url if "/apply" in job_url else job_url.rstrip("/") + "/apply"
        page.goto(apply_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        if detect_captcha(page):
            ss = take_screenshot(page, "lever_captcha")
            return "review_needed", ss

        unexpected = detect_unexpected_fields(page)
        if unexpected:
            ss = take_screenshot(page, "lever_unexpected")
            return "review_needed", f"Unexpected fields: {unexpected} — {ss}"

        # --- Personal info ---
        safe_fill(page, "input[name='name']", f"{profile.first_name} {profile.last_name}")
        safe_fill(page, "input[name='email']", profile.email)
        safe_fill(page, "input[name='phone']", profile.phone)
        safe_fill(page, "input[name='org']", "")  # current company — leave blank
        safe_fill(page, "input[name='location']", "United States")

        # URLs
        safe_fill(page, "input[name='urls[LinkedIn]']", profile.linkedin)
        safe_fill(page, "input[name='urls[GitHub]']", profile.github)
        safe_fill(page, "input[name='urls[Portfolio]']", profile.github)

        # --- Resume upload ---
        resume_input = page.query_selector("input[type='file']")
        if resume_input:
            resume_input.set_input_files(resume_path)
            page.wait_for_timeout(1500)
        else:
            ss = take_screenshot(page, "lever_no_resume")
            return "review_needed", f"No file input — {ss}"

        # --- Custom questions (yes/no dropdowns) ---
        _handle_lever_custom_questions(page, profile)

        # --- Open-ended / trap questions ---
        company_name = job_url.split("/")[2] if job_url else "the company"
        fill_open_questions(page, profile, company_name, "", jd_snippet)

        # --- Submit ---
        submit = page.query_selector("button[type='submit'], input[type='submit']")
        if not submit:
            ss = take_screenshot(page, "lever_no_submit")
            return "review_needed", f"No submit button — {ss}"

        submit.click()
        page.wait_for_timeout(3000)

        content = page.content().lower()
        if any(x in content for x in ["thank you", "application received", "successfully", "submitted"]):
            return "applied", "success"

        if any(x in content for x in ["error", "required", "invalid"]):
            ss = take_screenshot(page, "lever_error")
            return "review_needed", f"Form error — {ss}"

        ss = take_screenshot(page, "lever_ambiguous")
        return "review_needed", f"Unclear outcome — {ss}"

    except Exception as e:
        try:
            ss = take_screenshot(page, "lever_exception")
        except Exception:
            ss = "no screenshot"
        return "failed", f"{e} — {ss}"


def _handle_lever_custom_questions(page: Page, profile: CandidateProfile) -> None:
    """Handle Lever custom yes/no questions about work auth."""
    try:
        selects = page.query_selector_all("select")
        for sel in selects:
            label_text = page.evaluate("""
                el => {
                    const label = document.querySelector(`label[for='${el.id}']`);
                    return label ? label.textContent : el.closest('.application-question')?.querySelector('label')?.textContent || '';
                }
            """, sel).lower()

            if any(kw in label_text for kw in ["authoriz", "eligible", "legally"]):
                try:
                    sel.select_option(label="Yes")
                except Exception:
                    sel.select_option(value="yes")
            elif any(kw in label_text for kw in ["sponsor", "visa"]):
                try:
                    sel.select_option(label="Yes")
                except Exception:
                    sel.select_option(value="yes")
    except Exception:
        pass
