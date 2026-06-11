"""Ashby ATS form filler."""

from playwright.sync_api import Page

from jobops.agents.apply.base import (
    ApplyResult, CandidateProfile,
    safe_fill, safe_select, take_screenshot,
    detect_captcha, detect_unexpected_fields,
    fill_open_questions,
)


def apply_ashby(page: Page, job_url: str, resume_path: str, profile: CandidateProfile, jd_snippet: str = "") -> tuple[ApplyResult, str]:
    """
    Fill and submit an Ashby application.
    Returns (result, reason/screenshot_path).
    """
    try:
        # Ashby job pages are at /job-id — the form is at /job-id/application
        if "/application" not in job_url:
            apply_url = job_url.rstrip("/") + "/application"
        else:
            apply_url = job_url
        page.goto(apply_url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

        if detect_captcha(page):
            ss = take_screenshot(page, "ashby_captcha")
            return "review_needed", ss

        unexpected = detect_unexpected_fields(page)
        if unexpected:
            ss = take_screenshot(page, "ashby_unexpected")
            return "review_needed", f"Unexpected fields: {unexpected} — {ss}"

        # --- Personal info ---
        safe_fill(page, "input[name='name']", f"{profile.first_name} {profile.last_name}")
        safe_fill(page, "input[name='_systemfield_name']", f"{profile.first_name} {profile.last_name}")
        safe_fill(page, "input[placeholder*='First']", profile.first_name)
        safe_fill(page, "input[placeholder*='Last']", profile.last_name)
        safe_fill(page, "input[name='email']", profile.email)
        safe_fill(page, "input[name='_systemfield_email']", profile.email)
        safe_fill(page, "input[name='phone']", profile.phone)
        safe_fill(page, "input[name='_systemfield_phone']", profile.phone)

        # LinkedIn / GitHub
        safe_fill(page, "input[name*='linkedin']", profile.linkedin)
        safe_fill(page, "input[placeholder*='LinkedIn']", profile.linkedin)
        safe_fill(page, "input[name*='github']", profile.github)
        safe_fill(page, "input[placeholder*='GitHub']", profile.github)
        safe_fill(page, "input[name*='website']", profile.github)
        safe_fill(page, "input[placeholder*='Website']", profile.github)

        # Location
        safe_fill(page, "input[name*='location']", "United States")
        safe_fill(page, "input[placeholder*='Location']", "United States")
        safe_fill(page, "input[placeholder*='City']", "United States")

        # --- Resume upload ---
        resume_input = page.query_selector("input[type='file']")
        if resume_input:
            resume_input.set_input_files(resume_path)
            page.wait_for_timeout(1500)
        else:
            ss = take_screenshot(page, "ashby_no_resume")
            return "review_needed", f"No file input — {ss}"

        # --- Custom questions ---
        _handle_ashby_questions(page, profile)

        # --- Open-ended / trap questions ---
        company_name = job_url.split("/")[2] if job_url else "the company"
        fill_open_questions(page, profile, company_name, "", jd_snippet)

        # --- Submit ---
        submit = page.query_selector("button[type='submit'], input[type='submit']")
        if not submit:
            # Ashby sometimes uses a button with specific text
            submit = page.query_selector("button:has-text('Submit'), button:has-text('Apply')")
        if not submit:
            ss = take_screenshot(page, "ashby_no_submit")
            return "review_needed", f"No submit button — {ss}"

        submit.click()
        page.wait_for_timeout(3000)

        content = page.content().lower()
        if any(x in content for x in ["thank you", "application received", "successfully", "submitted", "we'll be in touch"]):
            return "applied", "success"

        if any(x in content for x in ["error", "required", "invalid", "please fill"]):
            ss = take_screenshot(page, "ashby_error")
            return "review_needed", f"Form error — {ss}"

        ss = take_screenshot(page, "ashby_ambiguous")
        return "review_needed", f"Unclear outcome — {ss}"

    except Exception as e:
        try:
            ss = take_screenshot(page, "ashby_exception")
        except Exception:
            ss = "no screenshot"
        return "failed", f"{e} — {ss}"


def _handle_ashby_questions(page: Page, profile: CandidateProfile) -> None:
    """Handle Ashby custom yes/no and work auth questions."""
    try:
        # Dropdowns
        selects = page.query_selector_all("select")
        for sel in selects:
            label_text = page.evaluate("""
                el => {
                    const id = el.id;
                    if (id) {
                        const lbl = document.querySelector(`label[for='${id}']`);
                        if (lbl) return lbl.textContent;
                    }
                    return el.closest('[class*="field"]')?.querySelector('label')?.textContent
                        || el.closest('[class*="question"]')?.querySelector('label')?.textContent
                        || '';
                }
            """, sel).lower()

            if any(kw in label_text for kw in ["authoriz", "eligible", "legally", "work in the"]):
                try:
                    sel.select_option(label="Yes")
                except Exception:
                    sel.select_option(value="yes")
            elif any(kw in label_text for kw in ["sponsor", "visa"]):
                try:
                    sel.select_option(label="Yes")
                except Exception:
                    sel.select_option(value="yes")

        # Radio buttons
        radios = page.query_selector_all("input[type='radio']")
        for radio in radios:
            label = page.evaluate("""
                el => {
                    return el.closest('label')?.textContent
                        || document.querySelector(`label[for='${el.id}']`)?.textContent
                        || '';
                }
            """, radio).strip().lower()
            val = (radio.get_attribute("value") or "").lower()
            if val in ("yes", "true", "1") and any(
                kw in label for kw in ["authoriz", "eligible", "legally", "sponsor", "visa"]
            ):
                radio.click()
    except Exception:
        pass
