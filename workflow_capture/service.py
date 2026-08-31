import json
import secrets
from pathlib import Path

from .database import connect, migrate, persist, read_task, similar_tasks
from .errors import ConfirmationError
from .redaction import sanitize
from .util import digest, utc_now
from .validation import validate_candidate


def prepare(candidate):
    validate_candidate(candidate)
    sanitized, findings = sanitize(candidate)
    validate_candidate(sanitized)
    token = secrets.token_urlsafe(24)
    payload_hash = digest(sanitized)
    inferred = [i for i, step in enumerate(sanitized["steps"], 1) if step["provenance"] == "ai_inferred"]
    return {
        "artifact_type": "workflow_capture_confirmation",
        "artifact_version": 1,
        "status": "awaiting_human_confirmation",
        "prepared_at": utc_now(),
        "confirmation_token": token,
        "confirmation_token_hash": digest(token.encode("utf-8")),
        "confirmed_payload_hash": payload_hash,
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


def commit(confirmation, token, db_path):
    if confirmation.get("status") != "awaiting_human_confirmation":
        raise ConfirmationError("confirmation artifact is not awaiting confirmation")
    if digest(token.encode("utf-8")) != confirmation.get("confirmation_token_hash"):
        raise ConfirmationError("confirmation token does not match the prepared artifact")
    payload = confirmation.get("payload")
    validate_candidate(payload)
    sanitized, findings = sanitize(payload)
    if findings:
        raise ConfirmationError("edited confirmation contains newly introduced sensitive data; prepare it again")
    if digest(payload) != confirmation.get("confirmed_payload_hash"):
        raise ConfirmationError("confirmed payload changed after preparation; prepare it again")
    connection = connect(db_path)
    try:
        task_id, duplicate = persist(connection, payload, confirmation["confirmation_token_hash"])
        stored = read_task(connection, task_id)
        if not stored or stored["confirmed_payload_hash"] != confirmation["confirmed_payload_hash"]:
            raise ConfirmationError("read-back verification failed")
        return {"status": "persisted", "task_id": task_id, "idempotent_hit": duplicate, "confirmed_payload_hash": stored["confirmed_payload_hash"], "read_back_ok": True, "schema_version": stored["schema_version"], "database": str(Path(db_path).resolve())}
    finally:
        connection.close()


def show(db_path, task_id):
    connection = connect(db_path)
    try:
        migrate(connection)
        return read_task(connection, task_id)
    finally:
        connection.close()


def similar(db_path, task_type, limit=10):
    connection = connect(db_path)
    try:
        return similar_tasks(connection, task_type, limit)
    finally:
        connection.close()


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

