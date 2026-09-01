import json
import os
from pathlib import Path

from .authorization import (
    ENV_ASSERTION,
    TRUST_CLASS_DEVELOPMENT,
    enforce_candidate_within_context,
    inject_trusted_context,
    load_grant,
    require_enterprise_capture,
    verify_capture_assertion,
)
from .errors import CaptureError, CaptureStorageError, ConfirmationError, StorageError
from .redaction import sanitize
from .storage import resolve_adapter
from .util import payload_digest
from .validation import validate_candidate, validate_enterprise_untrusted


def prepare(candidate, db_path):
    validate_candidate(candidate)
    sanitized, findings = sanitize(candidate)
    validate_candidate(sanitized)
    adapter = resolve_adapter(db_path)
    confirmation_id, payload_hash, prepared_at = adapter.create_confirmation(sanitized)
    inferred = [i for i, step in enumerate(sanitized["steps"], 1) if step["provenance"] == "ai_inferred"]
    return {
        "artifact_type": "workflow_capture_confirmation",
        "artifact_version": 2,
        "status": "PREPARED",
        "confirmation_id": confirmation_id,
        "prepared_at": prepared_at,
        "payload_hash": payload_hash,
        "redactions": [{"category": f.category, "path": f.path} for f in findings],
        "inferred_step_ordinals": inferred,
        "payload": sanitized,
        "confirmation_summary": {
            "task_type": sanitized["task_type"],
            "task_goal": sanitized["task_goal"],
            "step_count": len(sanitized["steps"]),
            "adoption_status": sanitized["final_result"]["adoption_status"],
            "redaction_count": len(findings),
        },
    }


def confirm(artifact, db_path, method, identity=None, source=None):
    if artifact.get("status") != "PREPARED":
        raise ConfirmationError("artifact is not PREPARED")
    payload = artifact.get("payload")
    validate_candidate(payload)
    sanitized, findings = sanitize(payload)
    if findings or sanitized != payload:
        raise ConfirmationError("artifact contains newly introduced sensitive data; prepare it again")
    if payload_digest(payload) != artifact.get("payload_hash"):
        raise ConfirmationError("payload changed after preparation; prepare it again")
    adapter = resolve_adapter(db_path)
    row = adapter.confirm_confirmation(
        artifact["confirmation_id"], artifact["payload_hash"],
        method=method, identity=identity, source=source,
    )
    confirmed = dict(artifact)
    confirmed.update({
        "status": "CONFIRMED",
        "confirmed_at": row["confirmed_at"],
        "confirmation_method": row["confirmation_method"],
        "confirmation_identity": row["confirmation_identity"],
        "confirmation_source": row["confirmation_source"],
    })
    return confirmed


def commit(confirmation, db_path):
    if confirmation.get("status") != "CONFIRMED":
        raise ConfirmationError("artifact is not CONFIRMED")
    payload = confirmation.get("payload")
    validate_candidate(payload)
    sanitized, findings = sanitize(payload)
    if findings or sanitized != payload:
        raise ConfirmationError("confirmed artifact contains newly introduced sensitive data; prepare it again")
    if payload_digest(payload) != confirmation.get("payload_hash"):
        raise ConfirmationError("confirmed payload changed; prepare and confirm it again")
    adapter = resolve_adapter(db_path)
    task_id, duplicate = adapter.persist_confirmed(confirmation["confirmation_id"], confirmation["payload_hash"])
    stored = adapter.read_task(task_id)
    state = adapter.read_confirmation(confirmation["confirmation_id"])
    if not stored or stored["confirmed_payload_hash"] != confirmation["payload_hash"]:
        raise ConfirmationError("read-back verification failed")
    if not state or state["status"] != "CONSUMED" or state["task_id"] != task_id:
        raise ConfirmationError("confirmation consumption verification failed")
    return {
        "status": "PERSISTED", "task_id": task_id, "confirmation_id": confirmation["confirmation_id"],
        "confirmation_status": state["status"], "confirmation_consumed_at": state["consumed_at"],
        "idempotent_payload_hit": duplicate, "confirmed_payload_hash": stored["confirmed_payload_hash"],
        "read_back_ok": True, "schema_version": stored["schema_version"],
        "database": str(Path(db_path).resolve()) if db_path else adapter.kind,
    }


def capture(candidate, db_path=None, env=None):
    """Enterprise-managed one-shot capture.

    Trusted chain: validate the untrusted candidate → obtain and verify the
    harness assertion (fail closed) → build the VerifiedHarnessCaptureContext →
    check the candidate against the verified scope → inject harness-owned
    session/context → sanitize → validate the final record → persist
    idempotently → read-back verify. The candidate can never supply
    authorization, session identity, or harness-provenance context.

    When no assertion is configured, the legacy local grant path runs in
    DEVELOPMENT_TEST_ONLY trust class (never production authority). Storage
    failure is reported honestly as TASK_COMPLETED_CAPTURE_FAILED and never
    disguised as either task failure or successful persistence.
    """
    env = os.environ if env is None else env
    validate_candidate(candidate)
    adapter = resolve_adapter(db_path, env=env)
    if (env.get(ENV_ASSERTION) or "").strip():
        validate_enterprise_untrusted(candidate)
        context = verify_capture_assertion(env=env)
        enforce_candidate_within_context(candidate, context, adapter.kind)
        merged = inject_trusted_context(candidate, context)
        authorization_record = context.public_record()
        trust_class = context.trust_class
    else:
        grant = load_grant(env=env)
        authorization_record = require_enterprise_capture(grant, candidate, adapter.kind)
        merged = candidate
        trust_class = TRUST_CLASS_DEVELOPMENT
    sanitized, findings = sanitize(merged)
    validate_candidate(sanitized)
    try:
        persisted = adapter.persist_authorized(sanitized, authorization_record)
    except StorageError as exc:
        raise CaptureStorageError(f"capture persistence failed on adapter '{adapter.kind}': {exc}")
    except OSError as exc:
        raise CaptureStorageError(f"capture persistence failed on adapter '{adapter.kind}': {exc}")
    except CaptureError:
        raise
    except Exception as exc:
        raise CaptureStorageError(
            f"capture persistence failed on adapter '{adapter.kind}' ({exc.__class__.__name__})"
        )
    if persisted.get("pending"):
        return {
            "status": "TASK_COMPLETED_CAPTURE_PENDING",
            "capture_mode": "ENTERPRISE_MANAGED_CAPTURE",
            "capture_session_id": sanitized.get("capture_session_id"),
            "storage": adapter.kind,
            "authorization": authorization_record,
            "trust_class": trust_class,
            "read_back_ok": False,
        }
    task_id = persisted["task_id"]
    try:
        stored = adapter.read_task(task_id)
    except Exception as exc:
        raise CaptureStorageError(
            f"capture read-back failed on adapter '{adapter.kind}' ({exc.__class__.__name__})"
        )
    if not stored or stored["confirmed_payload_hash"] != payload_digest(sanitized):
        raise CaptureStorageError("capture read-back verification failed; persistence is not claimed")
    capture_info = stored.get("capture", {})
    if capture_info.get("capture_status") != "TASK_COMPLETED_CAPTURE_PERSISTED":
        raise CaptureStorageError("stored record does not prove persisted status; persistence is not claimed")
    return {
        "status": "TASK_COMPLETED_CAPTURE_PERSISTED",
        "capture_mode": "ENTERPRISE_MANAGED_CAPTURE",
        "task_id": task_id,
        "capture_session_id": sanitized.get("capture_session_id"),
        "idempotent_replay": bool(persisted.get("duplicate")),
        "confirmed_payload_hash": stored["confirmed_payload_hash"],
        "schema_version": stored["schema_version"],
        "storage": adapter.kind,
        "authorization": authorization_record,
        "trust_class": trust_class,
        "redactions": [{"category": f.category, "path": f.path} for f in findings],
        "read_back_ok": True,
    }


def show(db_path, task_id):
    adapter = resolve_adapter(db_path)
    adapter.ensure_schema()
    return adapter.read_task(task_id)


def similar(db_path, task_type, limit=10):
    adapter = resolve_adapter(db_path)
    return adapter.similar_tasks(task_type, limit)


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
