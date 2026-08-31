import hashlib
import json
import uuid
from datetime import datetime, timezone


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    raw = value if isinstance(value, bytes) else canonical_json(value).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def new_id(prefix):
    return f"{prefix}_{uuid.uuid4()}"


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_label(value):
    return " ".join(str(value).strip().lower().split())

