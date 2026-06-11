"""Google Drive uploader for tailored resume PDFs."""

import json
import os

import httplib2
import google_auth_httplib2
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def _unverified_http():
    return httplib2.Http(disable_ssl_certificate_validation=True)


def _get_service():
    """Build Drive service using stored OAuth2 user credentials (refresh token)."""
    token_json = os.environ.get("GOOGLE_DRIVE_TOKEN_JSON")
    if not token_json:
        raise RuntimeError(
            "GOOGLE_DRIVE_TOKEN_JSON not set. Run: python -m jobops drive auth"
        )
    token_data = json.loads(token_json)
    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data["refresh_token"],
        token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        scopes=_SCOPES,
    )
    http = _unverified_http()
    authorized_http = google_auth_httplib2.AuthorizedHttp(creds, http=http)
    return build("drive", "v3", cache_discovery=False, http=authorized_http)


def run_auth_flow() -> dict:
    """
    Run OAuth2 flow to get user credentials. Prints URL, waits for code.
    Returns token dict to store in GOOGLE_DRIVE_TOKEN_JSON env var.
    """
    sa_raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not sa_raw:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON not set")
    sa = json.loads(sa_raw)

    # Build OAuth2 client config from service account project
    client_config = {
        "installed": {
            "client_id": os.environ.get("GOOGLE_OAUTH_CLIENT_ID", ""),
            "client_secret": os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", ""),
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, scopes=_SCOPES)
    creds = flow.run_console()
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
    }


def upload_resume(pdf_path: str, filename: str) -> str:
    """
    Upload a PDF to Google Drive folder.
    Returns the shareable view URL.
    """
    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    if not folder_id:
        raise RuntimeError("GOOGLE_DRIVE_FOLDER_ID not set")

    service = _get_service()
    file_metadata = {"name": filename, "parents": [folder_id]}
    media = MediaFileUpload(pdf_path, mimetype="application/pdf")
    uploaded = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, webViewLink",
    ).execute()

    file_id = uploaded["id"]
    # Make it readable by anyone with the link
    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()

    return uploaded.get("webViewLink", f"https://drive.google.com/file/d/{file_id}/view")
