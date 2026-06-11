"""Ashby ATS form filler."""

from playwright.sync_api import Page

from jobops.agents.apply.base import (
    ApplyResult, CandidateProfile,
    safe_fill, take_screenshot,
    detect_captcha, detect_unexpected_fields,
    fill_open_questions, _get_label_for,
)


def apply_ashby(page: Page, job_url: str, resume_path: str, profile: CandidateProfile, jd_snippet: str = "") -> tuple[ApplyResult, str]:
    """
    Fill and submit an Ashby application.
    Returns (result, reason/screenshot_path).
    """
    try:
        # Ashby job listing is at /job-id — the application form is at /job-id/application
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
        safe_fill(page, "input[name='_systemfield_name']", f"{profile.first_name} {profile.last_name}")
        safe_fill(page, "input[name='name']", f"{profile.first_name} {profile.last_name}")
        safe_fill(page, "input[name='_systemfield_email']", profile.email)
        safe_fill(page, "input[name='email']", profile.email)

        # Phone — Ashby uses UUID field names; target by type
        phone_el = page.query_selector("input[type='tel']")
        if phone_el:
            phone_el.fill(profile.phone)

        # LinkedIn — Ashby URL field
        url_el = page.query_selector("input[type='url']")
        if url_el:
            url_el.fill(profile.linkedin)

        # Location (if present)
        safe_fill(page, "input[name*='location']", "United States", timeout=1000)
        safe_fill(page, "input[placeholder*='Location']", "United States", timeout=1000)

        # --- Education (typeahead + text fields) ---
        _fill_education(page)

        # --- Resume upload ---
        # Ashby has 3 file inputs: [0]=autofill-from-resume, [1]=Resume, [2]=Cover Letter
        # We need index 1 (the actual Resume field)
        uploaded = _upload_resume(page, resume_path)
        if not uploaded:
            ss = take_screenshot(page, "ashby_no_resume")
            return "review_needed", f"Could not find Resume file input — {ss}"

        # --- Work auth / sponsorship radio ---
        _handle_ashby_questions(page)

        # --- Open-ended / trap questions ---
        company_name = _extract_company(job_url)
        fill_open_questions(page, profile, company_name, "", jd_snippet)

        page.wait_for_timeout(1000)
        ss_before = take_screenshot(page, "ashby_before_submit")

        # --- Submit ---
        # Ashby's submit button has no type="submit" — match by text
        submit = None
        for text in ["Submit Application", "Submit", "Apply"]:
            try:
                submit = page.get_by_role("button", name=text, exact=False).first
                if submit and submit.is_visible():
                    break
                submit = None
            except Exception:
                pass
        if not submit:
            submit = page.query_selector("button[type='submit']")
        if not submit:
            ss = take_screenshot(page, "ashby_no_submit")
            return "review_needed", f"No submit button — {ss}"

        submit.click()
        page.wait_for_timeout(5000)

        # Check for validation errors FIRST (fields highlighted red)
        errors = _detect_form_errors(page)
        if errors:
            ss = take_screenshot(page, "ashby_validation_error")
            return "review_needed", f"Validation errors: {errors} — {ss}"

        content = page.content().lower()
        # Ashby success pages say "your application has been submitted" or "thank you for applying"
        success_signals = [
            "your application has been submitted",
            "thank you for applying",
            "application received",
            "we've received your application",
            "successfully submitted",
        ]
        if any(x in content for x in success_signals):
            take_screenshot(page, "ashby_success")
            return "applied", "success"

        # Check URL changed to a confirmation page
        if "confirmation" in page.url or "success" in page.url or "thank" in page.url:
            take_screenshot(page, "ashby_success_url")
            return "applied", "success"

        ss = take_screenshot(page, "ashby_ambiguous")
        return "review_needed", f"Unclear outcome — {ss}"

    except Exception as e:
        try:
            ss = take_screenshot(page, "ashby_exception")
        except Exception:
            ss = "no screenshot"
        return "failed", f"{e} — {ss}"


def _upload_resume(page: Page, resume_path: str) -> bool:
    """
    Find the Resume-labeled file input (not the autofill slot or cover letter).
    Ashby file inputs: [0]=autofill, [1]=Resume (required), [2]=Cover Letter (optional).
    """
    file_inputs = page.query_selector_all("input[type='file']")
    for fi in file_inputs:
        heading = page.evaluate("""el => {
            let node = el;
            for (let depth = 0; depth < 8; depth++) {
                node = node.parentElement;
                if (!node) break;
                const prev = node.previousElementSibling;
                if (prev && prev.innerText && prev.innerText.trim()) {
                    return prev.innerText.trim().substring(0, 80);
                }
                const lbl = node.querySelector('h1,h2,h3,h4,h5,label');
                if (lbl && lbl.innerText && lbl.innerText.trim() && lbl !== el) {
                    return lbl.innerText.trim().substring(0, 80);
                }
            }
            return '';
        }""", fi)
        if "resume" in heading.lower() and "autofill" not in heading.lower():
            fi.set_input_files(resume_path)
            page.wait_for_timeout(2000)
            return True

    # Fallback: use index 1 if it exists (skip autofill at 0)
    if len(file_inputs) >= 2:
        file_inputs[1].set_input_files(resume_path)
        page.wait_for_timeout(2000)
        return True

    return False


def _fill_education(page: Page) -> None:
    """Fill education typeahead and text fields."""
    try:
        school_input = page.query_selector("input[placeholder*='Search schools']")
        if school_input:
            school_input.fill("University of Central Florida")
            page.wait_for_timeout(1500)
            # Click first dropdown suggestion
            try:
                option = page.query_selector("[role='option'], [role='listitem'], .dropdown-item")
                if option:
                    option.click()
                    page.wait_for_timeout(500)
            except Exception:
                pass

        degree_el = page.query_selector("input[placeholder*='Bachelor']")
        if degree_el:
            degree_el.fill("Master of Science")

        field_el = page.query_selector("input[placeholder*='Computer Science'], input[placeholder*='Field of Study']")
        if field_el:
            field_el.fill("Computer Science")
    except Exception:
        pass


def _handle_ashby_questions(page: Page) -> None:
    """
    Handle Ashby sponsorship/work-auth questions.
    Ashby renders these as styled Yes/No button groups (not radio inputs).
    She is on STEM OPT — no sponsorship needed to start, so click No for sponsorship.
    """
    try:
        buttons = page.query_selector_all("button")
        for btn in buttons:
            text = (btn.inner_text() or "").strip().lower()
            if text not in ("yes", "no"):
                continue

            # Get surrounding question context (walk up DOM)
            question_ctx = page.evaluate("""el => {
                let node = el;
                for (let i = 0; i < 6; i++) {
                    node = node.parentElement;
                    if (!node) break;
                    const txt = node.innerText || '';
                    if (txt.length > 20 && txt.length < 500) return txt.toLowerCase();
                }
                return '';
            }""", btn)

            # Sponsorship — click No
            if text == "no" and "sponsor" in question_ctx:
                btn.click()
                page.wait_for_timeout(300)
            # Work auth — click Yes
            elif text == "yes" and any(kw in question_ctx for kw in ["authoriz", "eligible", "legally"]):
                btn.click()
                page.wait_for_timeout(300)

        # Fallback: radio inputs
        for radio in page.query_selector_all("input[type='radio']"):
            label = page.evaluate("""el => {
                return el.closest('label')?.innerText
                    || document.querySelector(`label[for='${el.id}']`)?.innerText || '';
            }""", radio).strip().lower()
            if "no" in label and "sponsor" in label:
                radio.click()
            elif any(kw in label for kw in ["authoriz", "eligible", "legally"]) and "yes" in label:
                radio.click()

        # Fallback: selects
        for sel in page.query_selector_all("select"):
            label_text = page.evaluate("""el => {
                if (el.id) {
                    const lbl = document.querySelector(`label[for='${el.id}']`);
                    if (lbl) return lbl.innerText;
                }
                return el.closest('[class*=\"field\"]')?.querySelector('label')?.innerText || '';
            }""", sel).lower()
            if any(kw in label_text for kw in ["authoriz", "eligible", "legally"]):
                try:
                    sel.select_option(label="Yes")
                except Exception:
                    sel.select_option(value="yes")
    except Exception:
        pass


def _detect_form_errors(page: Page) -> list[str]:
    """Detect validation error messages shown after failed submit."""
    errors = []
    try:
        error_els = page.query_selector_all("[class*='error'], [class*='invalid'], [aria-invalid='true']")
        for el in error_els:
            txt = (el.inner_text() or "").strip()
            if txt and len(txt) < 200:
                errors.append(txt[:80])
    except Exception:
        pass
    return errors


def _extract_company(job_url: str) -> str:
    """Extract company name from Ashby URL: jobs.ashbyhq.com/COMPANY/..."""
    try:
        parts = job_url.split("/")
        # ashbyhq.com/collective/... → 'collective'
        for i, p in enumerate(parts):
            if "ashbyhq" in p and i + 1 < len(parts):
                return parts[i + 1].replace("-", " ").title()
    except Exception:
        pass
    return "the company"
