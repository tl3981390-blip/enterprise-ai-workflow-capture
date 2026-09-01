"""Reference in-memory implementation of the Storage Adapter Contract.

Proves the contract is implementable beyond LOCAL_SQLITE and that the runtime
is storage-agnostic. Used only by tests; contains no credentials and performs
no I/O.
"""

from workflow_capture.errors import CaptureError, ConfirmationError
from workflow_capture.util import new_id, payload_digest, utc_now


class MemoryAdapter:
    kind = "memory_reference"

    def __init__(self):
        self.confirmations = {}
        self.tasks = {}
        self.sessions = {}

    def health(self):
        return {"adapter": self.kind, "integrity_check": "ok"}

    def ensure_schema(self):
        return 4

    def create_confirmation(self, payload):
        confirmation_id = new_id("confirm")
        payload_hash = payload_digest(payload)
        prepared_at = utc_now()
        self.confirmations[confirmation_id] = {
            "confirmation_id": confirmation_id,
            "payload": payload,
            "payload_hash": payload_hash,
            "prepared_at": prepared_at,
            "status": "PREPARED",
            "confirmed_at": None,
            "confirmation_method": None,
            "confirmation_identity": None,
            "confirmation_source": None,
            "consumed_at": None,
            "task_id": None,
        }
        return confirmation_id, payload_hash, prepared_at

    def read_confirmation(self, confirmation_id):
        row = self.confirmations.get(confirmation_id)
        return dict(row) if row else None

    def confirm_confirmation(self, confirmation_id, expected_payload_hash, method, identity=None, source=None):
        row = self.confirmations.get(confirmation_id)
        if not row or row["status"] != "PREPARED" or row["payload_hash"] != expected_payload_hash:
            raise ConfirmationError("confirmation is missing, changed, or no longer PREPARED")
        row["status"] = "CONFIRMED"
        row["confirmed_at"] = utc_now()
        row["confirmation_method"] = method
        row["confirmation_identity"] = identity
        row["confirmation_source"] = source
        return dict(row)

    def _insert_task(self, payload, payload_hash, mode, authorization_record):
        session_id = payload.get("capture_session_id")
        if session_id and session_id in self.sessions:
            task_id = self.sessions[session_id]
            if self.tasks[task_id]["confirmed_payload_hash"] != payload_hash:
                raise CaptureError("capture_session_id reused with a different payload")
            return task_id, True
        for task_id, record in self.tasks.items():
            if record["confirmed_payload_hash"] == payload_hash:
                return task_id, True
        task_id = new_id("task")
        self.tasks[task_id] = {
            "task_id": task_id,
            "schema_version": 4,
            "created_at": utc_now(),
            "confirmed_payload_hash": payload_hash,
            "payload": payload,
            "task_type_normalized": " ".join(str(payload["task_type"]).strip().lower().split()),
            "adoption_status": payload["final_result"]["adoption_status"],
            "capture": {
                "capture_session_id": session_id,
                "capture_mode": mode,
                "capture_status": "TASK_COMPLETED_CAPTURE_PERSISTED",
                "authorization": authorization_record or {},
            },
        }
        if session_id:
            self.sessions[session_id] = task_id
        return task_id, False

    def persist_confirmed(self, confirmation_id, expected_payload_hash):
        row = self.confirmations.get(confirmation_id)
        if not row or row["status"] != "CONFIRMED" or row["payload_hash"] != expected_payload_hash:
            raise ConfirmationError("confirmation has not occurred, changed, or was already consumed")
        task_id, duplicate = self._insert_task(row["payload"], row["payload_hash"], "PERSONAL_EXPLICIT_CAPTURE", None)
        row["status"] = "CONSUMED"
        row["consumed_at"] = utc_now()
        row["task_id"] = task_id
        return task_id, duplicate

    def persist_authorized(self, payload, authorization_record):
        payload_hash = payload_digest(payload)
        task_id, duplicate = self._insert_task(payload, payload_hash, "ENTERPRISE_MANAGED_CAPTURE", authorization_record)
        return {"task_id": task_id, "duplicate": duplicate, "payload_hash": payload_hash}

    def read_task(self, task_id):
        record = self.tasks.get(task_id)
        return dict(record) if record else None

    def similar_tasks(self, task_type, limit=10):
        normalized = " ".join(str(task_type).strip().lower().split())
        matches = [r for r in self.tasks.values() if r["task_type_normalized"] == normalized]
        matches.sort(key=lambda r: r["created_at"], reverse=True)
        return [
            {"task_id": r["task_id"], "task_type": r["payload"]["task_type"], "adoption_status": r["adoption_status"]}
            for r in matches[:limit]
        ]

    def verify_evidence_chains(self):
        return {"status": "ok", "checked_events": 0, "legacy_unverified_events": 0, "failed_event_ids": []}


def create_adapter():
    return MemoryAdapter()
