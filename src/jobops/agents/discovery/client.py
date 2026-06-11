"""HTTP client for the Fantastic.jobs API."""

import os
from typing import Any

import httpx

BASE_URL = "https://data.fantastic.jobs/v1/"


def _get_api_key() -> str:
    key = os.environ.get("FANTASTIC_JOBS_API_KEY", "")
    if not key:
        raise RuntimeError("FANTASTIC_JOBS_API_KEY env variable is not set")
    return key


def _fetch_paginated(endpoint: str, params: dict[str, Any]) -> list[dict]:
    """Fetch all pages from an endpoint."""
    api_key = _get_api_key()
    headers = {"Authorization": f"Bearer {api_key}"}
    url = BASE_URL + endpoint

    results: list[dict] = []
    limit = params.get("limit", 1000)
    offset = params.get("offset", 0)

    with httpx.Client(timeout=30) as client:
        while True:
            page_params = {**params, "offset": offset}
            response = client.get(url, headers=headers, params=page_params)
            response.raise_for_status()
            data = response.json()

            # API may return a list directly or a dict with a results key
            if isinstance(data, list):
                page = data
            elif isinstance(data, dict):
                page = data.get("results", data.get("data", data.get("jobs", [])))
            else:
                page = []

            results.extend(page)

            if len(page) < limit:
                break
            offset += limit

    return results


def fetch_ats_jobs(
    time_frame: str = "24h",
    title_filter: str = "",
    location: str = "United States",
    limit: int = 1000,
    offset: int = 0,
) -> list[dict]:
    """Fetch jobs from the active-ats endpoint."""
    params: dict[str, Any] = {
        "time_frame": time_frame,
        "title": title_filter,
        "location": location,
        "limit": limit,
        "offset": offset,
        "description_format": "text",
        "include_basic_organization_details": "true",
    }
    return _fetch_paginated("active-ats", params)


def fetch_jb_jobs(
    time_frame: str = "24h",
    title_filter: str = "",
    location: str = "United States",
    limit: int = 1000,
    offset: int = 0,
) -> list[dict]:
    """Fetch jobs from the active-jb endpoint (job boards: LinkedIn, Wellfound, YC)."""
    params: dict[str, Any] = {
        "time_frame": time_frame,
        "title": title_filter,
        "location": location,
        "limit": limit,
        "offset": offset,
        "description_format": "text",
        # include_basic_organization_details not supported on active-jb
    }
    return _fetch_paginated("active-jb", params)
