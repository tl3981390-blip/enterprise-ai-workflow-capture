"""Reusable Storage Adapter Contract test suite.

Any adapter — LOCAL_SQLITE, the in-memory reference, or a real enterprise
adapter at deployment — must pass these same tests. Subclass and provide
`make_adapter()`.
"""

import unittest

from workflow_capture.errors import CaptureError, ConfirmationError


def contract_payload(task_type="contract-review", session=None):
    payload = {
        "task_type": task_type,
        "task_goal": "Review a contract for risky clauses",
        "process_summary": "Reviewed and corrected one clause.",
        "prerequisites": ["contract draft"],
        "steps": [
            {"actor": "human", "event_type": "action", "summary": "Supplied the draft.", "provenance": "observed"},
            {"actor": "ai", "event_type": "result", "summary": "Produced the review.", "provenance": "observed"},
        ],
        "final_result": {"summary": "Review notes", "adoption_status": "adopted"},
        "evidence": [{"evidence_type": "conversation_excerpt", "source_ref": "current-session:1", "sanitized_excerpt": "Minimal excerpt", "provenance": "observed"}],
    }
    if session:
        payload["capture_session_id"] = session
    return payload


class AdapterContractTests:
    """Mixin: subclasses provide make_adapter() and unittest.TestCase behavior."""

    def make_adapter(self):
        raise NotImplementedError

    def test_personal_confirmation_round_trip(self):
        adapter = self.make_adapter()
        payload = contract_payload()
        confirmation_id, payload_hash, prepared_at = adapter.create_confirmation(payload)
        self.assertTrue(confirmation_id and payload_hash and prepared_at)
        row = adapter.confirm_confirmation(confirmation_id, payload_hash, method="contract_test")
        self.assertEqual(row["status"], "CONFIRMED")
        task_id, duplicate = adapter.persist_confirmed(confirmation_id, payload_hash)
        self.assertFalse(duplicate)
        stored = adapter.read_task(task_id)
        self.assertEqual(stored["confirmed_payload_hash"], payload_hash)

    def test_confirmation_consumed_once(self):
        adapter = self.make_adapter()
        confirmation_id, payload_hash, _ = adapter.create_confirmation(contract_payload())
        adapter.confirm_confirmation(confirmation_id, payload_hash, method="contract_test")
        adapter.persist_confirmed(confirmation_id, payload_hash)
        with self.assertRaises(ConfirmationError):
            adapter.persist_confirmed(confirmation_id, payload_hash)

    def test_authorized_persist_is_idempotent_per_session(self):
        adapter = self.make_adapter()
        payload = contract_payload(session="contract-session-1")
        first = adapter.persist_authorized(payload, {"grant_id": "g1"})
        replay = adapter.persist_authorized(payload, {"grant_id": "g1"})
        self.assertEqual(first["task_id"], replay["task_id"])
        self.assertFalse(first["duplicate"])
        self.assertTrue(replay["duplicate"])

    def test_session_conflict_is_refused(self):
        adapter = self.make_adapter()
        adapter.persist_authorized(contract_payload(session="contract-session-2"), {"grant_id": "g1"})
        conflicting = contract_payload(session="contract-session-2")
        conflicting["task_goal"] = "A different payload under the same session"
        with self.assertRaises(CaptureError):
            adapter.persist_authorized(conflicting, {"grant_id": "g1"})

    def test_read_task_and_similar(self):
        adapter = self.make_adapter()
        persisted = adapter.persist_authorized(contract_payload(session="contract-session-3"), {"grant_id": "g1"})
        stored = adapter.read_task(persisted["task_id"])
        self.assertEqual(stored["payload"]["task_type"], "contract-review")
        matches = adapter.similar_tasks("contract-review", 10)
        self.assertTrue(any(m["task_id"] == persisted["task_id"] for m in matches))

    def test_verify_chains_and_schema(self):
        adapter = self.make_adapter()
        adapter.persist_authorized(contract_payload(session="contract-session-4"), {"grant_id": "g1"})
        self.assertEqual(adapter.verify_evidence_chains()["status"], "ok")
        self.assertIsInstance(adapter.ensure_schema(), int)


class SQLiteContractTests(AdapterContractTests, unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path

        from workflow_capture.storage.sqlite_adapter import SQLiteAdapter

        self.temp = tempfile.TemporaryDirectory()
        self._adapter = SQLiteAdapter(Path(self.temp.name) / "contract.db")

    def tearDown(self):
        self.temp.cleanup()

    def make_adapter(self):
        return self._adapter


class MemoryContractTests(AdapterContractTests, unittest.TestCase):
    def make_adapter(self):
        from fixtures.memory_adapter import MemoryAdapter

        return MemoryAdapter()


if __name__ == "__main__":
    unittest.main()
