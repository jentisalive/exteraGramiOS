#!/usr/bin/env python3
"""Generate build credentials from Actions secrets without logging their values."""
import json
import os
import re
from pathlib import Path


def configure(path):
    api_id = os.environ.get("TELEGRAM_API_ID", "")
    api_hash = os.environ.get("TELEGRAM_API_HASH", "")
    if not api_id.isdecimal() or int(api_id) <= 0 or not re.fullmatch(r"[a-fA-F0-9]{32}", api_hash):
        raise SystemExit("Set valid TELEGRAM_API_ID and TELEGRAM_API_HASH repository secrets before building the client.")
    value = {
        "bundle_id": "org.jentisalive.exteragram",
        "api_id": api_id, "api_hash": api_hash, "team_id": "EXTERA0000",
        "app_center_id": "0", "is_internal_build": "true", "is_appstore_build": "false",
        "appstore_id": "0", "app_specific_url_scheme": "exteragram",
        "premium_iap_product_id": "", "enable_siri": False, "enable_icloud": False,
    }
    Path(path).write_text(json.dumps(value))
    Path(path).chmod(0o600)


if __name__ == "__main__":
    import sys
    configure(sys.argv[1])
