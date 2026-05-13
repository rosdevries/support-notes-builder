"""SFMC Marketing Cloud REST API client.

Wraps the calls we use against Content Builder:

* OAuth 2.0 server-to-server token exchange (client credentials grant).
* Asset upload (HTML email, HTML email template, image).
* Asset search by name within a folder (used to detect existing
  per-speaker headshots and existing language templates so we don't
  re-upload duplicates).
* Asset patch (used by `replace_image_bytes` to update an existing
  speaker headshot in place rather than create a new one each time).

Mirrors the patterns proven out in the Expert Series Webinar Invite
Builder repo's `builder/sfmc_client.py`.

API references
--------------
* Authentication:        https://developer.salesforce.com/docs/marketing/marketing-cloud/guide/access-token-app-installed-package.html
* Asset model:           https://developer.salesforce.com/docs/marketing/marketing-cloud/guide/Asset.html
* Asset types:           https://developer.salesforce.com/docs/marketing/marketing-cloud/guide/Asset.html#assetTypes
  We use:
    - id 207 / name "htmlemail"        — the rendered email asset
    - id 208 / name "templatebasedemail" (NB: not used; we generate flat htmlemail)
    - id 4   / name "template"          — uploaded HTML email template
    - id 28  / name "image"             — speaker headshots
* Asset query:           POST /asset/v1/content/assets/query
"""

from __future__ import annotations

import base64
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests
from slugify import slugify

# ---------------------------------------------------------------------------
# Asset type IDs — pulled from the SFMC Asset Types reference.
# ---------------------------------------------------------------------------

ASSET_TYPE_HTMLEMAIL = {"name": "htmlemail", "id": 208}
ASSET_TYPE_TEMPLATE_EMAIL = {"name": "templatebasedemail", "id": 207}
ASSET_TYPE_TEMPLATE = {"name": "template", "id": 4}
ASSET_TYPE_IMAGE_PNG = {"name": "png", "id": 28}
ASSET_TYPE_IMAGE_JPG = {"name": "jpg", "id": 23}


def _asset_type_for_filename(filename: str) -> Dict[str, Any]:
    """Return the SFMC asset-type dict for the given filename's extension."""
    fn = filename.lower()
    if fn.endswith((".jpg", ".jpeg")):
        return ASSET_TYPE_IMAGE_JPG
    return ASSET_TYPE_IMAGE_PNG


# ---------------------------------------------------------------------------
# Auth — module-level token cache so we don't hit /v2/token on every call.
# ---------------------------------------------------------------------------

_TOKEN_CACHE: Dict[str, Any] = {"token": None, "expires_at": 0.0}


def _env(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        raise RuntimeError(
            f"Required environment variable {key!r} is not set. "
            f"Add it to .streamlit/secrets.toml or .env."
        )
    return val


def get_access_token() -> str:
    """Return a valid access token, refreshing if expired (with 60s safety margin)."""
    now = time.time()
    if _TOKEN_CACHE["token"] and _TOKEN_CACHE["expires_at"] > now + 60:
        return _TOKEN_CACHE["token"]

    auth_base = _env("MC_AUTH_BASE_URI").rstrip("/")
    payload = {
        "grant_type": "client_credentials",
        "client_id": _env("MC_CLIENT_ID"),
        "client_secret": _env("MC_CLIENT_SECRET"),
    }
    # Account ID is required for installed packages tied to a Business Unit.
    if os.environ.get("MC_ACCOUNT_ID", "").strip():
        payload["account_id"] = os.environ["MC_ACCOUNT_ID"].strip()

    resp = requests.post(f"{auth_base}/v2/token", json=payload, timeout=20)
    resp.raise_for_status()
    body = resp.json()
    _TOKEN_CACHE["token"] = body["access_token"]
    _TOKEN_CACHE["expires_at"] = now + int(body.get("expires_in", 1080))
    return _TOKEN_CACHE["token"]


def _rest_base() -> str:
    return _env("MC_REST_BASE_URI").rstrip("/")


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {get_access_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ---------------------------------------------------------------------------
# Asset query — find existing assets by name within a folder.
# ---------------------------------------------------------------------------

def find_asset_by_name(name: str, folder_id: int) -> Optional[Dict[str, Any]]:
    """Search a Content Builder folder for an asset with the given name.

    Uses the simple-query endpoint with an exact-match filter.  Returns the
    first hit (there should be at most one — names within a folder are unique
    in our convention) or None.
    """
    body = {
        "page": {"page": 1, "pageSize": 1},
        "query": {
            "leftOperand": {
                "property": "name",
                "simpleOperator": "equal",
                "value": name,
            },
            "logicalOperator": "AND",
            "rightOperand": {
                "property": "category.id",
                "simpleOperator": "equal",
                "value": folder_id,
            },
        },
    }
    resp = requests.post(
        f"{_rest_base()}/asset/v1/content/assets/query",
        json=body,
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    items = resp.json().get("items", [])
    return items[0] if items else None


def find_speaker_image(speaker_name: str, folder_id: int) -> Optional[str]:
    """Return the CDN URL for a speaker's headshot asset, or None if not found.

    We name speaker headshots ``{slug}-headshot`` where slug is a kebab-case
    transliteration of the speaker's name.  This means that if the same speaker
    appears in a future month's email, the UI can pre-fill the existing image
    instead of asking the user to re-upload.
    """
    if not speaker_name.strip():
        return None
    asset_name = f"{slugify(speaker_name, lowercase=True)}-headshot"
    asset = find_asset_by_name(asset_name, folder_id)
    if not asset:
        return None
    # The CDN URL lives at ``fileProperties.publishedURL`` for image assets.
    fp = asset.get("fileProperties") or {}
    return fp.get("publishedURL") or None


# ---------------------------------------------------------------------------
# Image upload — used for speaker headshots.
# ---------------------------------------------------------------------------

def replace_image_bytes(
    image_bytes: bytes,
    speaker_name: str,
    folder_id: int,
    source_filename: str,
) -> str:
    """Upload (or replace) a speaker headshot, return the CDN URL.

    Behaviour:

    * If an asset already exists with the conventional name in the target
      folder, PATCH it with the new bytes — keeps the asset ID stable so any
      previously sent emails still resolve the same CDN URL.
    * Otherwise POST a new image asset.

    The returned URL is the SFMC image CDN ``publishedURL``, suitable for use
    directly in ``<img src=...>`` of the rendered HTML email.
    """
    if not image_bytes:
        raise ValueError("image_bytes is empty")
    if not speaker_name.strip():
        raise ValueError("speaker_name is required")

    asset_name = f"{slugify(speaker_name, lowercase=True)}-headshot"
    asset_type = _asset_type_for_filename(source_filename)
    b64 = base64.b64encode(image_bytes).decode("ascii")

    payload: Dict[str, Any] = {
        "name": asset_name,
        "assetType": asset_type,
        "category": {"id": folder_id},
        "file": b64,
        "fileProperties": {"fileName": source_filename},
    }

    existing = find_asset_by_name(asset_name, folder_id)
    if existing:
        # PATCH replaces the binary in place.
        url = f"{_rest_base()}/asset/v1/content/assets/{existing['id']}"
        resp = requests.patch(url, json=payload, headers=_headers(), timeout=60)
    else:
        url = f"{_rest_base()}/asset/v1/content/assets"
        resp = requests.post(url, json=payload, headers=_headers(), timeout=60)

    if resp.status_code >= 400:
        raise RuntimeError(
            f"SFMC image upload failed ({resp.status_code}): {resp.text[:500]}"
        )
    body = resp.json()
    cdn_url = (body.get("fileProperties") or {}).get("publishedURL")
    if not cdn_url:
        raise RuntimeError(f"SFMC response missing fileProperties.publishedURL: {body}")
    return cdn_url


# ---------------------------------------------------------------------------
# Template asset upload — used by the bootstrap CLI.
# ---------------------------------------------------------------------------

def upsert_template(name: str, html: str, folder_id: int) -> Dict[str, Any]:
    """Create or update a Content Builder HTML template asset.

    Returns the full asset record (including ``id``, which is what callers
    persist as the per-language ``MC_TEMPLATE_ID_*`` value).
    """
    payload: Dict[str, Any] = {
        "name": name,
        "assetType": ASSET_TYPE_TEMPLATE,
        "category": {"id": folder_id},
        "content": html,
    }
    existing = find_asset_by_name(name, folder_id)
    if existing:
        url = f"{_rest_base()}/asset/v1/content/assets/{existing['id']}"
        resp = requests.patch(url, json=payload, headers=_headers(), timeout=60)
    else:
        url = f"{_rest_base()}/asset/v1/content/assets"
        resp = requests.post(url, json=payload, headers=_headers(), timeout=60)

    if resp.status_code >= 400:
        raise RuntimeError(
            f"SFMC template upsert failed ({resp.status_code}): {resp.text[:500]}"
        )
    return resp.json()


# ---------------------------------------------------------------------------
# Email asset creation — the headline operation.
# ---------------------------------------------------------------------------

@dataclass
class EmailAsset:
    """Result of a successful email-asset creation."""
    id: int
    name: str
    customer_key: str | None
    response: Dict[str, Any]


def create_html_email(
    *,
    name: str,
    subject: str,
    preheader: str,
    html: str,
    text: str = "",
    folder_id: int,
    template_id: Optional[int] = None,
) -> EmailAsset:
    """Create a flat HTML email asset in Content Builder.

    Notes
    -----
    * We pass the rendered HTML directly in ``content`` and use asset type
      ``htmlemail`` (id 208).  This is what the webinar project uses and what
      Content Builder accepts for fully-rendered emails generated outside
      the visual editor.
    * The subject and preheader live under ``views.html.meta``.
    * If a ``template_id`` is provided, it is recorded under
      ``views.html.template`` so the email shows up in Content Builder linked
      to the per-language template (helpful for editors).
    """
    views: Dict[str, Any] = {
        "html": {
            "content": html,
            "meta": {
                "subject": subject,
                "preheader": preheader,
            },
        },
        "text": {"content": text},
        "subjectline": {"content": subject},
        "preheader": {"content": preheader},
    }
    if template_id:
        views["html"]["template"] = {"id": template_id}

    payload: Dict[str, Any] = {
        "name": name,
        "assetType": ASSET_TYPE_HTMLEMAIL,
        "category": {"id": folder_id},
        "views": views,
    }

    url = f"{_rest_base()}/asset/v1/content/assets"
    resp = requests.post(url, json=payload, headers=_headers(), timeout=60)

    if resp.status_code == 400:
        suggested = _extract_suggested_name(resp)
        if suggested:
            payload["name"] = suggested
            resp = requests.post(url, json=payload, headers=_headers(), timeout=60)

    if resp.status_code >= 400:
        raise RuntimeError(
            f"SFMC email creation failed ({resp.status_code}): {resp.text[:500]}"
        )
    body = resp.json()
    return EmailAsset(
        id=int(body["id"]),
        name=body.get("name", name),
        customer_key=body.get("customerKey"),
        response=body,
    )


def create_template_based_email(
    *,
    name: str,
    subject: str,
    preheader: str,
    slots: Dict[str, str],
    text: str = "",
    folder_id: int,
    template_id: int,
) -> EmailAsset:
    """Create a template-based email asset (type 207) in Content Builder.

    Each entry in `slots` maps a slot key (matching the template's
    ``data-key`` attribute) to its pre-rendered HTML string.  Content Builder
    stores the slots as independent editable regions so editors can open the
    email in the visual editor and adjust any slot without touching raw HTML.

    Unlike ``create_html_email`` this function does NOT send a monolithic
    ``views.html.content`` string — the rendered layout is reconstructed by
    Content Builder from the template + individual slot objects at preview/send
    time.
    """
    slot_objects = {k: {"content": v} for k, v in slots.items()}
    views: Dict[str, Any] = {
        "html": {
            "meta": {"subject": subject, "preheader": preheader},
            "template": {"id": template_id},
            "slots": slot_objects,
        },
        "text": {"content": text},
        "subjectline": {"content": subject},
        "preheader": {"content": preheader},
    }
    payload: Dict[str, Any] = {
        "name": name,
        "assetType": ASSET_TYPE_TEMPLATE_EMAIL,
        "category": {"id": folder_id},
        "views": views,
    }

    url = f"{_rest_base()}/asset/v1/content/assets"
    resp = requests.post(url, json=payload, headers=_headers(), timeout=60)

    if resp.status_code == 400:
        suggested = _extract_suggested_name(resp)
        if suggested:
            payload["name"] = suggested
            resp = requests.post(url, json=payload, headers=_headers(), timeout=60)

    if resp.status_code >= 400:
        raise RuntimeError(
            f"SFMC template email creation failed ({resp.status_code}): {resp.text[:500]}"
        )
    body = resp.json()
    return EmailAsset(
        id=int(body["id"]),
        name=body.get("name", name),
        customer_key=body.get("customerKey"),
        response=body,
    )


def _extract_suggested_name(resp: requests.Response) -> Optional[str]:
    """Parse a Suggested name from an SFMC 400 duplicate-name error, or return None."""
    try:
        body = resp.json()
        for verr in body.get("validationErrors", []):
            if verr.get("errorcode") == 118039:
                m = re.search(r"Suggested name:\s*(.+)", verr.get("message", ""))
                if m:
                    return m.group(1).strip()
    except Exception:
        pass
    return None
