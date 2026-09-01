"""Test fixture: an enterprise adapter that fails once with a simulated storage
timeout, then delegates to a real SQLite backend. Demonstrates that a capture
failure is reported honestly and that an idempotent retry with the same
capture_session_id persists exactly one task.

The marker and database paths come from the test environment and are confined
to the system temporary directory.
"""

import os
import tempfile
from pathlib import Path

from workflow_capture.errors import StorageError
from workflow_capture.storage.sqlite_adapter import SQLiteAdapter


def _confined(env_name):
    value = os.environ[env_name]
    resolved = Path(value).resolve()
    if tempfile.gettempdir() not in str(resolved):
        raise StorageError(f"{env_name} must point inside the system temporary directory")
    return resolved


class FlakyAdapter:
    kind = "enterprise_flaky"

    def __init__(self):
        self.state_marker = _confined("WORKFLOW_CAPTURE_FLAKY_STATE")
        self.inner = SQLiteAdapter(str(_confined("WORKFLOW_CAPTURE_FLAKY_DB")))

    def _fail_once(self):
        if not self.state_marker.exists():
            self.state_marker.write_text("failed-once", encoding="ascii")
            raise StorageError("simulated storage timeout")

    def health(self):
        return {"adapter": self.kind}

    def ensure_schema(self):
        return self.inner.ensure_schema()

    def create_confirmation(self, payload):
        return self.inner.create_confirmation(payload)

    def read_confirmation(self, confirmation_id):
        return self.inner.read_confirmation(confirmation_id)

    def confirm_confirmation(self, confirmation_id, expected_payload_hash, method, identity=None, source=None):
        return self.inner.confirm_confirmation(confirmation_id, expected_payload_hash, method, identity=identity, source=source)

    def persist_confirmed(self, confirmation_id, expected_payload_hash):
        return self.inner.persist_confirmed(confirmation_id, expected_payload_hash)

    def persist_authorized(self, payload, authorization_record):
        self._fail_once()
        return self.inner.persist_authorized(payload, authorization_record)

    def read_task(self, task_id):
        return self.inner.read_task(task_id)

    def similar_tasks(self, task_type, limit=10):
        return self.inner.similar_tasks(task_type, limit)

    def verify_evidence_chains(self):
        return self.inner.verify_evidence_chains()


def create_adapter():
    return FlakyAdapter()
