"""Download resume PDF from Google Drive to a local temp file."""

import os
import re
import tempfile

import httplib2
import google_auth_httplib2
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def _get_drive_service():
    import json
    token_json = os.environ.get("GOOGLE_DRIVE_TOKEN_JSON")
    if not token_json:
        raise RuntimeError("GOOGLE_DRIVE_TOKEN_JSON not set")
    token_data = json.loads(token_json)
    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data["refresh_token"],
        token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        scopes=_SCOPES,
    )
    http = httplib2.Http(disable_ssl_certificate_validation=True)
    authorized_http = google_auth_httplib2.AuthorizedHttp(creds, http=http)
    return build("drive", "v3", cache_discovery=False, http=authorized_http)


def _extract_file_id(drive_url: str) -> str:
    m = re.search(r"/file/d/([a-zA-Z0-9_-]+)", drive_url)
    if not m:
        raise ValueError(f"Cannot extract file ID from URL: {drive_url}")
    return m.group(1)


def download_resume(drive_url: str) -> str:
    """
    Download resume PDF from Drive URL to a temp file.
    Returns the local temp file path.
    """
    file_id = _extract_file_id(drive_url)
    service = _get_drive_service()

    request = service.files().get_media(fileId=file_id)
    tmp_dir = tempfile.gettempdir()
    tmp_path = os.path.join(tmp_dir, "srinijavaibhavi.pdf")
    with open(tmp_path, "wb") as f:
        f.write(request.execute())
    return tmp_path
