#!/usr/bin/env python3
"""LOCAL TESTING ONLY — issue a development grant signed with an env-held key.

This output is DEVELOPMENT_TEST_ONLY: it can never produce production
enterprise authority, and the runtime refuses it when
WORKFLOW_CAPTURE_MODE=PRODUCTION_ENTERPRISE. Production assertions are issued
by the harness/enterprise deployment with an asymmetric private key that never
appears in this repository or in the model's environment.

The signing key is read only from WORKFLOW_CAPTURE_AUTHORIZATION_KEY. Example:

    WORKFLOW_CAPTURE_AUTHORIZATION_KEY=<local-test-key> \
    python scripts/make_test_grant.py --output grant.json \
        --grant-id grant_local_001 --issuer local-test-harness \
        --task-types supplier-quote-comparison --departments procurement \
        --storage-adapter local_sqlite --days 90
"""

import argparse
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workflow_capture.authorization import ENV_GRANT_KEY, TRUST_CLASS_DEVELOPMENT
from workflow_capture.util import canonical_json


def main():
    parser = argparse.ArgumentParser(description="Issue a DEVELOPMENT_TEST_ONLY local grant (never production authority)")
    parser.add_argument("--output", required=True)
    parser.add_argument("--grant-id", required=True)
    parser.add_argument("--issuer", required=True)
    parser.add_argument("--mode", default="ENTERPRISE_MANAGED_CAPTURE")
    parser.add_argument("--task-types", nargs="+", default=["*"])
    parser.add_argument("--departments", nargs="+", default=["*"])
    parser.add_argument("--storage-adapter", default="local_sqlite")
    parser.add_argument("--retention-policy", default="local-testing")
    parser.add_argument("--days", type=int, default=90)
    args = parser.parse_args()
    key = os.environ.get(ENV_GRANT_KEY)
    if not key:
        raise SystemExit(f"{ENV_GRANT_KEY} is required to sign a local test grant")
    now = datetime.now(timezone.utc)
    grant = {
        "grant_version": 1,
        "grant_id": args.grant_id,
        "issuer": args.issuer,
        "mode": args.mode,
        "capture_authorized": True,
        "trust_class": TRUST_CLASS_DEVELOPMENT,
        "capture_scope": {"task_types": args.task_types, "departments": args.departments},
        "storage_scope": {"adapter": args.storage_adapter},
        "retention_policy": args.retention_policy,
        "issued_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(days=args.days)).isoformat().replace("+00:00", "Z"),
    }
    grant["signature"] = hmac.new(key.encode("utf-8"), canonical_json(grant).encode("utf-8"), hashlib.sha256).hexdigest()
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(grant, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "issued", "trust_class": TRUST_CLASS_DEVELOPMENT, "output": str(target), "grant_id": args.grant_id}, ensure_ascii=False))
    print("WARNING: this grant is DEVELOPMENT_TEST_ONLY and cannot authorize production enterprise capture", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
