"""Enterprise Capture Authorization — harness-attested trust boundary.

Core invariant: **model data is not harness-trusted data**. The host model may
submit task facts, but it can never create enterprise authority or
harness-owned context. Enterprise capture runs only under a verified
HARNESS_CAPTURE_ASSERTION:

- ``WORKFLOW_CAPTURE_ASSERTION`` — path to the per-capture assertion JSON,
  signed by the harness/enterprise private key (Ed25519). The signer lives
  entirely outside this Skill; this runtime only verifies.
- ``WORKFLOW_CAPTURE_TRUST_ROOT`` — path to the deployment-protected trust
  root JSON pinning trusted issuers to public keys. Neither the candidate nor
  any CLI flag can select the trust root, verifier, issuer, or keys.
- ``WORKFLOW_CAPTURE_MODE`` — optional explicit trust class enforcement:
  ``PRODUCTION_ENTERPRISE`` or ``DEVELOPMENT_TEST``.

A successful verification yields a :class:`VerifiedHarnessCaptureContext` —
the only object allowed to carry ``capture_session_id`` and harness-owned
``business_context``/``ai_context``. The candidate can never supply them.

Development path (``WORKFLOW_CAPTURE_AUTHORIZATION_FILE`` grants): retained
for local testing only, mechanically stamped ``DEVELOPMENT_TEST_ONLY``; it is
refused outright when ``WORKFLOW_CAPTURE_MODE=PRODUCTION_ENTERPRISE``. An
unsigned or HMAC grant can never produce production-trusted persistence.
"""

import base64
import binascii
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .errors import AuthorizationError
from .util import canonical_json, normalize_label, parse_iso8601, utc_now

# Development/testing grant channel (never production authority).
ENV_GRANT_FILE = "WORKFLOW_CAPTURE_AUTHORIZATION_FILE"
ENV_GRANT_KEY = "WORKFLOW_CAPTURE_AUTHORIZATION_KEY"

# Attested enterprise channel.
ENV_ASSERTION = "WORKFLOW_CAPTURE_ASSERTION"
ENV_TRUST_ROOT = "WORKFLOW_CAPTURE_TRUST_ROOT"
ENV_MODE = "WORKFLOW_CAPTURE_MODE"

MODE_ENTERPRISE = "ENTERPRISE_MANAGED_CAPTURE"
MODE_PERSONAL = "PERSONAL_EXPLICIT_CAPTURE"
CAPTURE_MODES = {MODE_ENTERPRISE, MODE_PERSONAL}

TRUST_PRODUCTION = "PRODUCTION_ENTERPRISE"
TRUST_DEVELOPMENT = "DEVELOPMENT_TEST"
TRUST_CLASS_PRODUCTION = "PRODUCTION_ENTERPRISE"
TRUST_CLASS_DEVELOPMENT = "DEVELOPMENT_TEST_ONLY"
TRUST_CLASSES = {TRUST_CLASS_PRODUCTION, TRUST_CLASS_DEVELOPMENT}

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

REQUIRED_ASSERTION_FIELDS = (
    "assertion_version",
    "assertion_id",
    "issuer",
    "capture_authorized",
    "mode",
    "capture_session_id",
    "capture_scope",
    "storage_scope",
    "retention_policy",
    "issued_at",
    "expires_at",
    "nonce",
    "signature",
)

SIGNATURE_FIELD = "signature"


def _read_json_file(path_value, what):
    if not path_value or not str(path_value).strip():
        raise AuthorizationError(f"{what} is not configured; capture is fail-closed")
    try:
        data = json.loads(Path(path_value).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthorizationError(f"{what} is unreadable or malformed: {exc.__class__.__name__}")
    if not isinstance(data, dict):
        raise AuthorizationError(f"{what} must be a JSON object")
    return data


def _check_time_bounds(data, what):
    now = datetime.now(timezone.utc)
    expires_at = parse_iso8601(data.get("expires_at"))
    if expires_at is None:
        raise AuthorizationError(f"{what} expires_at is not a valid ISO-8601 timestamp")
    if expires_at <= now:
        raise AuthorizationError(f"{what} is expired")
    if parse_iso8601(data.get("issued_at")) is None:
        raise AuthorizationError(f"{what} issued_at is not a valid ISO-8601 timestamp")


def _scope_list(scope, key):
    values = (scope or {}).get(key, ["*"])
    if values == "*":
        return ["*"]
    if not isinstance(values, list):
        return []
    return [normalize_label(v) for v in values]


def _scope_allows(scope, key, value):
    allowed = _scope_list(scope, key)
    return "*" in allowed or normalize_label(value) in allowed


# ---------------------------------------------------------------------------
# Verified Harness Capture Context (production path)
# ---------------------------------------------------------------------------

_VERIFIED_MARKER = object()
"""Module-internal capability: a context object can only be constructed by the
verifier in this module after signature, issuer, expiry and scope checks pass.
A plain dict or candidate payload cannot become a VerifiedHarnessCaptureContext."""


class VerifiedHarnessCaptureContext:
    """Harness-trusted facts for one capture, created only by verification."""

    def __init__(self, _marker, *, assertion, trust_class, verification_method):
        if _marker is not _VERIFIED_MARKER:
            raise AuthorizationError("VerifiedHarnessCaptureContext cannot be constructed outside the verifier")
        self.assertion_id = assertion["assertion_id"]
        self.issuer = assertion["issuer"]
        self.verification_method = verification_method
        self.trust_class = trust_class
        self.capture_session_id = assertion["capture_session_id"]
        self.capture_scope = assertion["capture_scope"]
        self.storage_scope = assertion["storage_scope"]
        self.business_context = assertion.get("business_context") or {}
        self.ai_context = assertion.get("ai_context") or {}
        self.retention_policy = assertion["retention_policy"]
        self.issued_at = assertion["issued_at"]
        self.expires_at = assertion["expires_at"]
        self.verified_at = utc_now()

    def task_type_allowed(self, task_type):
        return _scope_allows(self.capture_scope, "task_types", task_type)

    def department_allowed(self, department):
        return _scope_allows(self.capture_scope, "departments", department)

    def storage_allowed(self, adapter_kind):
        expected = normalize_label((self.storage_scope or {}).get("adapter", ""))
        return bool(expected) and expected == normalize_label(adapter_kind)

    def public_record(self):
        """Persisted authorization record: verification level and provenance
        facts only — never keys, secrets, or verifier internals."""
        return {
            "assertion_id": self.assertion_id,
            "issuer": self.issuer,
            "mode": MODE_ENTERPRISE,
            "verification": self.verification_method,
            "trust_class": self.trust_class,
            "retention_policy": self.retention_policy,
            "verified_at": self.verified_at,
        }


def _ed25519_verify(public_key_b64, signature_b64, message):
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        raise AuthorizationError(
            "production assertion verification requires the 'cryptography' package; refusing to capture"
        )
    try:
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64, validate=True))
        signature = base64.b64decode(signature_b64, validate=True)
    except (ValueError, binascii.Error):
        raise AuthorizationError("assertion key or signature is not valid base64")
    try:
        public_key.verify(signature, message)
    except InvalidSignature:
        raise AuthorizationError("assertion signature verification failed")


def verify_capture_assertion(env=None):
    """Verify the harness capture assertion against the deployment trust root.

    Fail closed on any missing configuration, untrusted issuer, bad signature,
    expiry, or structural defect. Returns a VerifiedHarnessCaptureContext.
    """
    env = os.environ if env is None else env
    trust_root = _read_json_file(env.get(ENV_TRUST_ROOT), f"trust root ({ENV_TRUST_ROOT})")
    if trust_root.get("trust_root_version") != 1:
        raise AuthorizationError("trust root trust_root_version must be 1")
    trust_class = trust_root.get("trust_class")
    if trust_class not in TRUST_CLASSES:
        raise AuthorizationError(f"trust root trust_class must be one of {sorted(TRUST_CLASSES)}")
    trusted_issuers = trust_root.get("trusted_issuers")
    if not isinstance(trusted_issuers, dict) or not trusted_issuers:
        raise AuthorizationError("trust root pins no trusted issuers")

    mode = (env.get(ENV_MODE) or "").strip()
    if mode == TRUST_PRODUCTION and trust_class != TRUST_CLASS_PRODUCTION:
        raise AuthorizationError("PRODUCTION_ENTERPRISE mode requires a production-class trust root")
    if mode == TRUST_DEVELOPMENT and trust_class != TRUST_CLASS_DEVELOPMENT:
        raise AuthorizationError("DEVELOPMENT_TEST mode requires a DEVELOPMENT_TEST_ONLY trust root")
    if mode and mode not in {TRUST_PRODUCTION, TRUST_DEVELOPMENT}:
        raise AuthorizationError(f"{ENV_MODE} must be {TRUST_PRODUCTION} or {TRUST_DEVELOPMENT}")

    assertion = _read_json_file(env.get(ENV_ASSERTION), f"capture assertion ({ENV_ASSERTION})")
    missing = [field for field in REQUIRED_ASSERTION_FIELDS if field not in assertion]
    if missing:
        raise AuthorizationError(f"assertion is missing required fields: {', '.join(missing)}")
    if assertion.get("assertion_version") != 1:
        raise AuthorizationError("assertion_version must be 1")
    if assertion.get("capture_authorized") is not True:
        raise AuthorizationError("assertion does not authorize capture")
    if assertion.get("mode") != MODE_ENTERPRISE:
        raise AuthorizationError(f"assertion mode must be {MODE_ENTERPRISE}")
    if not isinstance(assertion.get("capture_scope"), dict) or not isinstance(assertion.get("storage_scope"), dict):
        raise AuthorizationError("assertion scopes must be JSON objects")
    if not str(assertion.get("capture_session_id", "")).strip():
        raise AuthorizationError("assertion must bind a capture_session_id")
    _check_time_bounds(assertion, "assertion")

    issuer = assertion["issuer"]
    pinned = trusted_issuers.get(issuer)
    if pinned is None:
        raise AuthorizationError("assertion issuer is not in the trusted trust root")
    if pinned.get("algorithm") != "Ed25519":
        raise AuthorizationError("trusted issuer algorithm must be Ed25519")
    key_id = assertion.get("key_id")
    if key_id and pinned.get("key_id") and key_id != pinned["key_id"]:
        raise AuthorizationError("assertion key_id does not match the pinned issuer key")
    signed = {k: v for k, v in assertion.items() if k != SIGNATURE_FIELD}
    _ed25519_verify(pinned.get("public_key", ""), str(assertion.get(SIGNATURE_FIELD, "")),
                    canonical_json(signed).encode("utf-8"))

    return VerifiedHarnessCaptureContext(
        _VERIFIED_MARKER,
        assertion=assertion,
        trust_class=trust_class,
        verification_method="asymmetric_signature_verified",
    )


def enforce_candidate_within_context(candidate, context, adapter_kind):
    """Check untrusted candidate facts against the verified context. Fail closed."""
    if not context.task_type_allowed(candidate.get("task_type", "")):
        raise AuthorizationError("task_type is outside the assertion's authorized capture scope")
    if not context.storage_allowed(adapter_kind):
        raise AuthorizationError(
            f"configured storage adapter '{adapter_kind}' is outside the assertion's authorized storage scope"
        )
    department = context.business_context.get("department")
    if department and not context.department_allowed(department):
        raise AuthorizationError("assertion business context is outside its own capture scope")
    candidate_ref = (candidate.get("business_context") or {}).get("ref")
    assertion_ref = context.business_context.get("business_context_ref")
    if assertion_ref and candidate_ref and str(candidate_ref) != str(assertion_ref):
        raise AuthorizationError("candidate business reference does not match the verified assertion")


def inject_trusted_context(candidate, context):
    """Build the final record input: untrusted task facts plus harness-owned
    identity and context injected from the verified assertion."""
    merged = dict(candidate)
    merged["capture_session_id"] = context.capture_session_id
    if context.business_context:
        context_fields = {
            "provenance": "harness_provided",
            **{k: v for k, v in context.business_context.items() if k != "business_context_ref"},
        }
        if context.business_context.get("business_context_ref"):
            context_fields["ref"] = context.business_context["business_context_ref"]
        merged["business_context"] = context_fields
    if context.ai_context:
        merged["ai_context"] = {**context.ai_context, "provenance": "harness_provided"}
    return merged


# ---------------------------------------------------------------------------
# Development/testing grant channel (never production authority)
# ---------------------------------------------------------------------------

class Grant:
    """Legacy local grant — DEVELOPMENT_TEST_ONLY. Cannot authorize production
    enterprise capture and is refused when PRODUCTION_ENTERPRISE is enforced."""

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

    def task_type_allowed(self, task_type):
        return _scope_allows(self.data.get("capture_scope"), "task_types", task_type)

    def department_allowed(self, department):
        return _scope_allows(self.data.get("capture_scope"), "departments", department)

    def storage_allowed(self, adapter_kind):
        expected = normalize_label((self.data.get("storage_scope") or {}).get("adapter", ""))
        return bool(expected) and expected == normalize_label(adapter_kind)

    def public_record(self):
        return {
            "grant_id": self.grant_id,
            "issuer": self.issuer,
            "mode": self.mode,
            "retention_policy": self.retention_policy,
            "verification": "development_test_only",
            "dev_mechanism": self.verification,
            "trust_class": TRUST_CLASS_DEVELOPMENT,
            "checked_at": utc_now(),
        }


def _verify_grant_signature(data, key):
    signed = {k: v for k, v in data.items() if k != SIGNATURE_FIELD}
    expected = hmac.new(key.encode("utf-8"), canonical_json(signed).encode("utf-8"), hashlib.sha256).hexdigest()
    supplied = str(data.get(SIGNATURE_FIELD, "")).strip().lower()
    return hmac.compare_digest(expected, supplied)


def load_grant(env=None):
    """Load a local development grant. Fail closed. Never production authority."""
    env = os.environ if env is None else env
    if (env.get(ENV_MODE) or "").strip() == TRUST_PRODUCTION:
        raise AuthorizationError(
            f"{TRUST_PRODUCTION} capture requires a verified harness assertion "
            f"({ENV_ASSERTION}); local grants are {TRUST_CLASS_DEVELOPMENT}"
        )
    data = _read_json_file(env.get(ENV_GRANT_FILE), f"authorization grant ({ENV_GRANT_FILE})")
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
        if not _verify_grant_signature(data, key):
            raise AuthorizationError("authorization grant signature verification failed")
        verification = "hmac_sha256_verified"
    else:
        if has_signature:
            raise AuthorizationError(
                "grant carries a signature but no verification key is configured; refusing unverifiable grant"
            )
        verification = "harness_asserted_unverified"

    _check_time_bounds(data, "authorization grant")
    return Grant(data, verification, env.get(ENV_GRANT_FILE))


def require_enterprise_capture(grant, candidate, adapter_kind):
    """Development-path scope enforcement. Returns a DEVELOPMENT_TEST_ONLY record."""
    if grant.mode != MODE_ENTERPRISE:
        raise AuthorizationError(
            f"grant mode {grant.mode} does not authorize enterprise-managed capture"
        )
    session_id = candidate.get("capture_session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise AuthorizationError(
            "development capture requires a capture_session_id for idempotent persistence"
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
