"""Render tailored resume dict → PDF via Jinja2 + WeasyPrint."""

import os
import tempfile

import yaml
from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup
from weasyprint import HTML

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
_FACTS_PATH = os.path.join(os.path.dirname(__file__), "../../../../facts.yaml")


def _load_static_facts() -> dict:
    with open(_FACTS_PATH) as f:
        return yaml.safe_load(f)["candidate"]


def render_pdf(tailored: dict, output_path: str, jd_raw: str = "") -> str:
    """
    Render a tailored resume dict to PDF.
    Returns the output_path on success.
    """
    facts = _load_static_facts()

    env = Environment(loader=FileSystemLoader(_TEMPLATE_DIR), autoescape=False)
    template = env.get_template("resume.html.j2")

    # Map skill keys to display labels
    skill_label_map = {
        "languages": "Languages",
        "frontend": "Frontend",
        "backend": "Backend & APIs",
        "databases": "Databases",
        "ai_ml": "AI & Agentic Systems",
        "cloud": "Cloud & Infra",
        "testing": "Testing & QA",
        "observability": "Observability",
    }
    skills_ordered = {}
    for key, label in skill_label_map.items():
        items = tailored.get("skills", {}).get(label) or tailored.get("skills", {}).get(key)
        if not items:
            # fallback to facts
            items = facts["skills"].get(key, [])
        if items:
            skills_ordered[label] = items

    context = {
        "name": facts["name"],
        "email": facts["email"],
        "phone": facts["phone"],
        "github": facts["github"],
        "linkedin": facts["linkedin"],
        "work_authorization": facts.get("work_authorization", ""),
        "summary": tailored.get("summary", ""),
        "skills": skills_ordered,
        "experience": tailored.get("experience", facts["experience"]),
        "volunteer": tailored.get("volunteer", facts.get("volunteer", [])) if tailored.get("include_volunteer", True) else [],
        "education": facts["education"],
        "projects": tailored.get("projects", facts.get("projects", [])) if tailored.get("include_projects", True) else [],
        "certifications": facts.get("certifications", []),
        "jd_raw": jd_raw,
    }

    html_content = template.render(**context)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    HTML(string=html_content).write_pdf(output_path)
    return output_path
