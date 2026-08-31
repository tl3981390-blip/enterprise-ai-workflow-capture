import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from workflow_capture.database import MIGRATIONS, connect, current_version, migrate
from workflow_capture.errors import ConfirmationError, MigrationError, ValidationError
from workflow_capture.service import commit, prepare, show, similar
from workflow_capture.util import digest


def candidate(task_type="complaint-response", adoption="adopted", steps=None):
    return {
        "task_type": task_type,
        "task_goal": "Resolve a customer complaint accurately",
        "process_summary": "A concise process reconstruction.",
        "prerequisites": ["complaint", "policy"],
        "steps": steps or [
            {"actor": "human", "event_type": "action", "summary": "Provided complaint context.", "provenance": "observed", "metadata": {"event_version": 1}},
            {"actor": "ai", "event_type": "result", "summary": "Drafted the response.", "provenance": "observed", "metadata": {"event_version": 1}},
        ],
        "final_result": {"summary": "A response draft", "adoption_status": adoption},
        "evidence": [{"evidence_type": "conversation_excerpt", "source_ref": "current-session:1", "sanitized_excerpt": "Minimal evidence", "provenance": "observed"}],
        "external_references": [],
        "harness_metadata": {"harness": "test"},
    }


class CaptureAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "workflow.db"

    def tearDown(self):
        self.temp.cleanup()

    def confirmed_commit(self, value):
        artifact = prepare(value)
        result = commit(artifact, artifact["confirmation_token"], self.db)
        return artifact, result

    def test_01_one_shot_success_and_read_back(self):
        artifact, result = self.confirmed_commit(candidate())
        self.assertTrue(result["read_back_ok"])
        stored = show(self.db, result["task_id"])
        self.assertEqual(stored["payload"], artifact["payload"])
        self.assertEqual(stored["confirmed_payload_hash"], artifact["confirmed_payload_hash"])

    def test_02_multi_turn_clarification_is_preserved(self):
        steps = candidate()["steps"]
        steps.insert(1, {"actor": "human", "event_type": "clarification", "summary": "Added the refund rule.", "provenance": "observed"})
        _, result = self.confirmed_commit(candidate(steps=steps))
        self.assertEqual(show(self.db, result["task_id"])["payload"]["steps"][1]["event_type"], "clarification")

    def test_03_ai_failure_human_correction_retry_recovery(self):
        steps = [
            {"actor": "ai", "event_type": "failure", "summary": "Used the wrong order date.", "provenance": "observed"},
            {"actor": "human", "event_type": "correction", "summary": "Provided the verified date.", "provenance": "observed"},
            {"actor": "ai", "event_type": "retry", "summary": "Retried the analysis.", "provenance": "observed"},
            {"actor": "ai", "event_type": "recovery", "summary": "Produced a corrected response.", "provenance": "observed"},
        ]
        _, result = self.confirmed_commit(candidate(steps=steps))
        types = [s["event_type"] for s in show(self.db, result["task_id"])["payload"]["steps"]]
        self.assertEqual(types, ["failure", "correction", "retry", "recovery"])

    def test_04_abandoned_failure(self):
        _, result = self.confirmed_commit(candidate(adoption="abandoned", steps=[{"actor": "ai", "event_type": "failure", "summary": "No authorized source was available.", "provenance": "observed"}]))
        self.assertEqual(show(self.db, result["task_id"])["payload"]["final_result"]["adoption_status"], "abandoned")

    def test_05_partial_adoption(self):
        _, result = self.confirmed_commit(candidate(adoption="partially_adopted"))
        self.assertEqual(show(self.db, result["task_id"])["payload"]["final_result"]["adoption_status"], "partially_adopted")

    def test_06_secrets_and_personal_data_are_redacted(self):
        value = candidate()
        synthetic_key = "sk-" + "TESTONLY1234567890abcdef"
        credential_label = "api_" + "key="
        value["steps"][0]["summary"] = f"{credential_label}{synthetic_key} email user@example.com phone 13800138000"
        artifact = prepare(value)
        text = json.dumps(artifact["payload"])
        self.assertNotIn(synthetic_key, text)
        self.assertNotIn("user@example.com", text)
        self.assertNotIn("13800138000", text)
        self.assertGreaterEqual(len(artifact["redactions"]), 3)

    def test_07_similar_tasks_use_disclosed_match_basis(self):
        self.confirmed_commit(candidate("Contract Review"))
        self.confirmed_commit(candidate("  contract   review ", adoption="partially_adopted"))
        self.confirmed_commit(candidate("invoice review"))
        matches = similar(self.db, "contract review")
        self.assertEqual(len(matches), 2)

    def test_08_human_edit_requires_fresh_prepare(self):
        artifact = prepare(candidate())
        artifact["payload"]["task_goal"] = "Corrected goal"
        with self.assertRaises(ConfirmationError):
            commit(artifact, artifact["confirmation_token"], self.db)
        refreshed = prepare(artifact["payload"])
        result = commit(refreshed, refreshed["confirmation_token"], self.db)
        self.assertEqual(show(self.db, result["task_id"])["payload"]["task_goal"], "Corrected goal")

    def test_09_same_task_type_different_paths_remain_distinct(self):
        first = candidate("contract-review")
        second = candidate("contract-review", steps=[
            {"actor": "human", "event_type": "action", "summary": "Provided policy before contract.", "provenance": "observed"},
            {"actor": "ai", "event_type": "result", "summary": "Completed review once.", "provenance": "observed"},
        ])
        self.confirmed_commit(first)
        self.confirmed_commit(second)
        paths = {row["path_signature"] for row in similar(self.db, "contract-review")}
        self.assertEqual(len(paths), 2)

    def test_10_lineage_and_future_analysis_foundation(self):
        _, result = self.confirmed_commit(candidate())
        connection = connect(self.db)
        try:
            evidence_count = connection.execute("SELECT COUNT(*) FROM evidence WHERE task_id=?", (result["task_id"],)).fetchone()[0]
            lineage_count = connection.execute("SELECT COUNT(*) FROM lineage").fetchone()[0]
            knowledge_table = connection.execute("SELECT 1 FROM sqlite_master WHERE name='derived_knowledge'").fetchone()
        finally:
            connection.close()
        self.assertEqual(evidence_count, 1)
        self.assertEqual(lineage_count, 1)
        self.assertIsNotNone(knowledge_table)

    def test_11_schema_v1_migrates_to_v2_and_old_data_reads(self):
        artifact = prepare(candidate())
        connection = connect(self.db)
        connection.executescript(MIGRATIONS[1])
        connection.execute("INSERT INTO schema_migrations VALUES (1, '2026-01-01T00:00:00Z', ?)", (digest(MIGRATIONS[1].encode()),))
        connection.commit()
        connection.close()
        result = commit(artifact, artifact["confirmation_token"], self.db)
        self.assertEqual(show(self.db, result["task_id"])["schema_version"], 2)
        connection = connect(self.db)
        try:
            self.assertEqual(current_version(connection), 2)
        finally:
            connection.close()


class BoundaryAndFailureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "workflow.db"

    def tearDown(self):
        self.temp.cleanup()

    def test_invalid_and_empty_input(self):
        with self.assertRaises(ValidationError):
            prepare({})
        value = candidate()
        value["steps"] = []
        with self.assertRaises(ValidationError):
            prepare(value)

    def test_wrong_token_and_new_secret_are_blocked(self):
        artifact = prepare(candidate())
        with self.assertRaises(ConfirmationError):
            commit(artifact, "wrong", self.db)
        artifact["payload"]["steps"][0]["summary"] = "password=" + "TEST_ONLY_SECRET"
        artifact["confirmed_payload_hash"] = digest(artifact["payload"])
        with self.assertRaises(ConfirmationError):
            commit(artifact, artifact["confirmation_token"], self.db)

    def test_duplicate_commit_is_idempotent(self):
        artifact = prepare(candidate())
        first = commit(artifact, artifact["confirmation_token"], self.db)
        second = commit(artifact, artifact["confirmation_token"], self.db)
        self.assertEqual(first["task_id"], second["task_id"])
        self.assertTrue(second["idempotent_hit"])

    def test_persistence_survives_reconnect_and_integrity_is_ok(self):
        artifact = prepare(candidate())
        result = commit(artifact, artifact["confirmation_token"], self.db)
        self.assertIsNotNone(show(self.db, result["task_id"]))
        connection = connect(self.db)
        try:
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        finally:
            connection.close()

    def test_newer_database_is_refused(self):
        connection = sqlite3.connect(self.db)
        connection.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT, checksum TEXT)")
        connection.execute("INSERT INTO schema_migrations VALUES (999, 'now', 'x')")
        connection.commit()
        connection.close()
        connection = connect(self.db)
        try:
            with self.assertRaises(MigrationError):
                migrate(connection)
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
