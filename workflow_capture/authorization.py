"""Enterprise Capture Authorization.

The authorization fact is supplied by the deploying harness/enterprise through
the environment, never by the candidate payload, a CLI flag, or conversation
content:

- ``WORKFLOW_CAPTURE_AUTHORIZATION_FILE`` — path to a harness-issued grant JSON.
- ``WORKFLOW_CAPTURE_AUTHORIZATION_KEY`` — optional HMAC-SHA256 verification key.
  When configured, every grant must carry a valid ``signature``. When absent, an
  unsigned grant is accepted as ``harness_asserted_unverified`` and recorded as
  such; a signed grant without a configured key is refused (unverifiable).

Every check fails closed: any missing, malformed, expired, out-of-scope or
unverifiable grant raises AuthorizationError and nothing is persisted.
"""

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .errors import AuthorizationError
from .util import canonical_json, normalize_label, parse_iso8601, utc_now

ENV_GRANT_FILE = "WORKFLOW_CAPTURE_AUTHORIZATION_FILE"
ENV_GRANT_KEY = "WORKFLOW_CAPTURE_AUTHORIZATION_KEY"

MODE_ENTERPRISE = "ENTERPRISE_MANAGED_CAPTURE"
MODE_PERSONAL = "PERSONAL_EXPLICIT_CAPTURE"
CAPTURE_MODES = {MODE_ENTERPRISE, MODE_PERSONAL}

CAPTURE_STATUSES = {
    "TASK_COMPLETED_CAPTURE_PERSISTED",
    "TASK_COMPLETED_CAPTURE_PENDING",
    "TASK_COMPLETED_CAPTURE_FAILED",
}

REQUIRED_GRANT_FIELDS = (
    "grant_version",
    "grant_id",
    "issuer",
    "mode",
    "capture_authorized",
    "capture_scope",
    "storage_scope",
    "retention_policy",
    "issued_at",
    "expires_at",
)

SIGNATURE_FIELD = "signature"


class Grant:
    def __init__(self, data, verification, source_path):
        self.data = data
        self.verification = verification
        self.source_path = source_path

    @property
    def grant_id(self):
        return self.data["grant_id"]

    @property
    def mode(self):
        return self.data["mode"]

    @property
    def issuer(self):
        return self.data["issuer"]

    @property
    def retention_policy(self):
        return self.data["retention_policy"]

    def _scope_values(self, key):
        scope = self.data.get("capture_scope") or {}
        values = scope.get(key, ["*"])
        if values == "*":
            return ["*"]
        if not isinstance(values, list):
            return []
        return [normalize_label(v) for v in values]

    def task_type_allowed(self, task_type):
        allowed = self._scope_values("task_types")
        return "*" in allowed or normalize_label(task_type) in allowed

    def department_allowed(self, department):
        allowed = self._scope_values("departments")
        return "*" in allowed or normalize_label(department) in allowed

    def storage_allowed(self, adapter_kind):
        scope = self.data.get("storage_scope") or {}
        expected = normalize_label(scope.get("adapter", ""))
        return bool(expected) and expected == normalize_label(adapter_kind)

    def public_record(self):
        """Authorization metadata persisted with the task. Contains no secrets."""
        return {
            "grant_id": self.grant_id,
            "issuer": self.issuer,
            "mode": self.mode,
            "retention_policy": self.retention_policy,
            "verification": self.verification,
            "checked_at": utc_now(),
        }


def _verify_signature(data, key):
    signed = {k: v for k, v in data.items() if k != SIGNATURE_FIELD}
    expected = hmac.new(key.encode("utf-8"), canonical_json(signed).encode("utf-8"), hashlib.sha256).hexdigest()
    supplied = str(data.get(SIGNATURE_FIELD, "")).strip().lower()
    return hmac.compare_digest(expected, supplied)


def load_grant(env=None):
    """Load and mechanically verify the harness-provided grant. Fail closed."""
    env = os.environ if env is None else env
    path = env.get(ENV_GRANT_FILE)
    if not path or not str(path).strip():
        raise AuthorizationError(
            "no enterprise capture authorization is configured "
            f"({ENV_GRANT_FILE} is unset); capture is fail-closed"
        )
    grant_path = Path(path)
    try:
        raw = grant_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthorizationError(f"authorization grant is unreadable or malformed: {exc.__class__.__name__}")
    if not isinstance(data, dict):
        raise AuthorizationError("authorization grant must be a JSON object")
    missing = [field for field in REQUIRED_GRANT_FIELDS if field not in data]
    if missing:
        raise AuthorizationError(f"authorization grant is missing required fields: {', '.join(missing)}")
    if data.get("capture_authorized") is not True:
        raise AuthorizationError("authorization grant does not authorize capture (capture_authorized is not true)")
    if data.get("mode") not in CAPTURE_MODES:
        raise AuthorizationError(f"authorization grant mode must be one of {sorted(CAPTURE_MODES)}")
    if not isinstance(data.get("capture_scope"), dict) or not isinstance(data.get("storage_scope"), dict):
        raise AuthorizationError("authorization grant scopes must be JSON objects")

    key = env.get(ENV_GRANT_KEY)
    has_signature = bool(str(data.get(SIGNATURE_FIELD, "")).strip())
    if key:
        if not has_signature:
            raise AuthorizationError("a verification key is configured but the grant is unsigned")
        if not _verify_signature(data, key):
            raise AuthorizationError("authorization grant signature verification failed")
        verification = "hmac_sha256_verified"
    else:
        if has_signature:
            raise AuthorizationError(
                "grant carries a signature but no verification key is configured; refusing unverifiable grant"
            )
        verification = "harness_asserted_unverified"

    now = datetime.now(timezone.utc)
    expires_at = parse_iso8601(data.get("expires_at"))
    if expires_at is None:
        raise AuthorizationError("authorization grant expires_at is not a valid ISO-8601 timestamp")
    if expires_at <= now:
        raise AuthorizationError("authorization grant is expired")
    if parse_iso8601(data.get("issued_at")) is None:
        raise AuthorizationError("authorization grant issued_at is not a valid ISO-8601 timestamp")
    return Grant(data, verification, str(grant_path))


def require_enterprise_capture(grant, candidate, adapter_kind):
    """Enforce that this specific capture is inside the grant. Fail closed."""
    if grant.mode != MODE_ENTERPRISE:
        raise AuthorizationError(
            f"grant mode {grant.mode} does not authorize enterprise-managed capture"
        )
    session_id = candidate.get("capture_session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise AuthorizationError(
            "enterprise-managed capture requires a harness-provided capture_session_id for idempotent persistence"
        )
    if not grant.task_type_allowed(candidate.get("task_type", "")):
        raise AuthorizationError("task_type is outside the authorized capture scope")
    if not grant.storage_allowed(adapter_kind):
        raise AuthorizationError(
            f"configured storage adapter '{adapter_kind}' is outside the authorized storage scope"
        )
    context = candidate.get("business_context")
    if isinstance(context, dict) and (context.get("department") or context.get("workflow")):
        if context.get("provenance") != "harness_provided":
            raise AuthorizationError(
                "department/workflow context is accepted only when legally provided by the harness"
            )
        department = context.get("department")
        if department and not grant.department_allowed(department):
            raise AuthorizationError("department context is outside the authorized capture scope")
    return grant.public_record()
