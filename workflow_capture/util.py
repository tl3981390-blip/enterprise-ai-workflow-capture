import hashlib
import json
import uuid
from datetime import datetime, timezone


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    raw = value if isinstance(value, bytes) else canonical_json(value).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def payload_digest(payload):
    """Content hash of a candidate payload.

    capture_session_id is a capture-identity key, not work content: it is
    excluded so that identical work retried under a different session still
    deduplicates by content, while the session id itself stays a unique
    idempotency key of its own.
    """
    if isinstance(payload, dict):
        payload = {k: v for k, v in payload.items() if k != "capture_session_id"}
    return digest(payload)


def new_id(prefix):
    return f"{prefix}_{uuid.uuid4()}"


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_label(value):
    return " ".join(str(value).strip().lower().split())


def parse_iso8601(value):
    """Parse an ISO-8601 timestamp string; returns an aware datetime or None.

    Accepts a trailing "Z" on all supported Python versions. Never raises:
    callers treat None as "not a valid timestamp".
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
