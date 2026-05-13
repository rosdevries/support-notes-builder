"""One-time template bootstrap — uploads the shared Support Notes template to SFMC.

A single template is used for all languages.  The ``<html lang="...">``
attribute is left as the neutral default in the template; ``email_builder``
injects the correct BCP-47 code into each rendered email at send time.

The template is created / updated in place (idempotent).  After running,
paste the printed asset ID into ``.env`` as ``MC_TEMPLATE_ID``.

Usage
-----
    python -m builder.bootstrap_template

    # To PATCH a known existing asset by ID instead of searching by name:
    python -m builder.bootstrap_template --asset-id 879310

Environment variables required
-------------------------------
    MC_TEMPLATE_FOLDER_ID   Content Builder folder where the template lives
    MC_*                    Standard SFMC OAuth vars (see .env.example)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

from builder import sfmc_client

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "support-notes-template.html"
TEMPLATE_NAME = "Support Notes - Email template"


def _patch_by_id(asset_id: int, html: str) -> dict:
    """PATCH an existing template asset by known ID — bypasses the name search."""
    payload = {
        "name": TEMPLATE_NAME,
        "assetType": sfmc_client.ASSET_TYPE_TEMPLATE,
        "content": html,
    }
    url = f"{sfmc_client._rest_base()}/asset/v1/content/assets/{asset_id}"
    resp = requests.patch(url, json=payload, headers=sfmc_client._headers(), timeout=60)
    if resp.status_code >= 400:
        raise RuntimeError(
            f"SFMC template PATCH failed ({resp.status_code}): {resp.text[:500]}"
        )
    return resp.json()


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--asset-id", type=int, default=None,
        help="SFMC asset ID of an existing template to PATCH (skips name search).",
    )
    args = parser.parse_args(argv)

    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    print(f"Template: {TEMPLATE_PATH.name}  ({len(html):,} chars)")

    if args.asset_id:
        print(f"PATCHing existing asset ID {args.asset_id} …")
        result = _patch_by_id(args.asset_id, html)
    else:
        folder_raw = os.environ.get("MC_TEMPLATE_FOLDER_ID", "").strip()
        if not folder_raw:
            print(
                "ERROR: MC_TEMPLATE_FOLDER_ID is not set. "
                "Add it to .env / Streamlit secrets, or pass --asset-id.",
                file=sys.stderr,
            )
            return 2
        folder_id = int(folder_raw)
        print(f"Upserting template in folder {folder_id} …")
        result = sfmc_client.upsert_template(
            name=TEMPLATE_NAME, html=html, folder_id=folder_id
        )

    asset_id = result["id"]
    print()
    print(f"OK — template asset ID: {asset_id}")
    print(f"   Add to your environment:  MC_TEMPLATE_ID={asset_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
