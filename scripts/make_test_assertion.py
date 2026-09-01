#!/usr/bin/env python3
"""LOCAL TESTING ONLY — mint an Ed25519-signed test capture assertion.

Generates a fresh throwaway keypair, writes a DEVELOPMENT_TEST_ONLY trust root
(public key only) and a signed assertion for exercising the full asymmetric
verification path locally. The private key never leaves the process and is
never persisted. This tool cannot mint a PRODUCTION_ENTERPRISE trust root:
production assertions are signed by the harness/enterprise deployment, outside
this Skill.

Example:

    python scripts/make_test_assertion.py --trust-root trust-root.json \
        --assertion assertion.json --issuer local-test-harness \
        --session test-session-001 --task-types supplier-quote-comparison \
        --departments procurement --storage-adapter local_sqlite \
        --department procurement --workflow sourcing --business-ref po-123
"""

import argparse
import base64
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workflow_capture.authorization import TRUST_CLASS_DEVELOPMENT, TRUST_CLASS_PRODUCTION
from workflow_capture.util import canonical_json


def main():
    parser = argparse.ArgumentParser(description="Mint a DEVELOPMENT_TEST_ONLY signed capture assertion")
    parser.add_argument("--trust-root", required=True)
    parser.add_argument("--assertion", required=True)
    parser.add_argument("--issuer", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--task-types", nargs="+", default=["*"])
    parser.add_argument("--departments", nargs="+", default=["*"])
    parser.add_argument("--storage-adapter", default="local_sqlite")
    parser.add_argument("--department")
    parser.add_argument("--workflow")
    parser.add_argument("--business-ref")
    parser.add_argument("--retention-policy", default="local-testing")
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--trust-class", default=TRUST_CLASS_DEVELOPMENT)
    args = parser.parse_args()

    if args.trust_class != TRUST_CLASS_DEVELOPMENT:
        raise SystemExit(
            f"this local test signer can only mint {TRUST_CLASS_DEVELOPMENT} assertions; "
            f"{TRUST_CLASS_PRODUCTION} assertions come from the harness/enterprise deployment"
        )

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    except ImportError:
        raise SystemExit("the 'cryptography' package is required to mint test assertions")

    private_key = Ed25519PrivateKey.generate()
    public_key_b64 = base64.b64encode(
        private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode("ascii")
    key_id = "test-key-" + base64.b16encode(canonical_json({"pk": public_key_b64}).encode())[-8:].decode().lower()

    now = datetime.now(timezone.utc)
    assertion = {
        "assertion_version": 1,
        "assertion_id": f"assertion-test-{now.strftime('%Y%m%d%H%M%S')}",
        "issuer": args.issuer,
        "key_id": key_id,
        "capture_authorized": True,
        "mode": "ENTERPRISE_MANAGED_CAPTURE",
        "capture_session_id": args.session,
        "capture_scope": {"task_types": args.task_types, "departments": args.departments},
        "storage_scope": {"adapter": args.storage_adapter},
        "retention_policy": args.retention_policy,
        "issued_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(days=args.days)).isoformat().replace("+00:00", "Z"),
        "nonce": base64.urlsafe_b64encode(canonical_json({"id": args.session, "at": str(now)}).encode())[:24].decode(),
    }
    business_context = {}
    if args.department:
        business_context["department"] = args.department
    if args.workflow:
        business_context["workflow"] = args.workflow
    if args.business_ref:
        business_context["business_context_ref"] = args.business_ref
    if business_context:
        assertion["business_context"] = business_context
    assertion["signature"] = base64.b64encode(
        private_key.sign(canonical_json(assertion).encode("utf-8"))
    ).decode("ascii")
    del private_key

    trust_root = {
        "trust_root_version": 1,
        "trust_class": TRUST_CLASS_DEVELOPMENT,
        "trusted_issuers": {
            args.issuer: {"algorithm": "Ed25519", "key_id": key_id, "public_key": public_key_b64}
        },
    }
    trust_path = Path(args.trust_root)
    trust_path.parent.mkdir(parents=True, exist_ok=True)
    trust_path.write_text(json.dumps(trust_root, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assertion_path = Path(args.assertion)
    assertion_path.parent.mkdir(parents=True, exist_ok=True)
    assertion_path.write_text(json.dumps(assertion, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "issued",
        "trust_class": TRUST_CLASS_DEVELOPMENT,
        "trust_root": str(trust_path),
        "assertion": str(assertion_path),
        "assertion_id": assertion["assertion_id"],
        "key_id": key_id,
    }, ensure_ascii=False))
    print("WARNING: DEVELOPMENT_TEST_ONLY — the private key was discarded and never persisted", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
