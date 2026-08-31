import json
from pathlib import Path

from .database import (
    confirm_confirmation,
    connect,
    create_confirmation,
    migrate,
    persist_confirmed,
    read_confirmation,
    read_task,
    similar_tasks,
)
from .errors import ConfirmationError
from .redaction import sanitize
from .util import digest
from .validation import validate_candidate


def prepare(candidate, db_path):
    validate_candidate(candidate)
    sanitized, findings = sanitize(candidate)
    validate_candidate(sanitized)
    connection = connect(db_path)
    try:
        confirmation_id, payload_hash, prepared_at = create_confirmation(connection, sanitized)
    finally:
        connection.close()
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
    if digest(payload) != artifact.get("payload_hash"):
        raise ConfirmationError("payload changed after preparation; prepare it again")
    connection = connect(db_path)
    try:
        row = confirm_confirmation(
            connection, artifact["confirmation_id"], artifact["payload_hash"],
            method=method, identity=identity, source=source,
        )
    finally:
        connection.close()
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
    if digest(payload) != confirmation.get("payload_hash"):
        raise ConfirmationError("confirmed payload changed; prepare and confirm it again")
    connection = connect(db_path)
    try:
        task_id, duplicate = persist_confirmed(connection, confirmation["confirmation_id"], confirmation["payload_hash"])
        stored = read_task(connection, task_id)
        state = read_confirmation(connection, confirmation["confirmation_id"])
        if not stored or stored["confirmed_payload_hash"] != confirmation["payload_hash"]:
            raise ConfirmationError("read-back verification failed")
        if not state or state["status"] != "CONSUMED" or state["task_id"] != task_id:
            raise ConfirmationError("confirmation consumption verification failed")
        return {
            "status": "PERSISTED", "task_id": task_id, "confirmation_id": confirmation["confirmation_id"],
            "confirmation_status": state["status"], "confirmation_consumed_at": state["consumed_at"],
            "idempotent_payload_hit": duplicate, "confirmed_payload_hash": stored["confirmed_payload_hash"],
            "read_back_ok": True, "schema_version": stored["schema_version"],
            "database": str(Path(db_path).resolve()),
        }
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
