import copy
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from workflow_capture.database import MIGRATIONS, connect, current_version, migrate, verify_evidence_chains
from workflow_capture.errors import ConfirmationError, MigrationError, ValidationError
from workflow_capture.service import commit, confirm, prepare, show, similar
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
        prepared = prepare(value, self.db)
        confirmed = confirm(prepared, self.db, method="test_explicit_human", identity="employee-test", source="test-harness")
        result = commit(confirmed, self.db)
        return confirmed, result

    def test_01_one_shot_success_and_read_back(self):
        artifact, result = self.confirmed_commit(candidate())
        self.assertTrue(result["read_back_ok"])
        stored = show(self.db, result["task_id"])
        self.assertEqual(stored["payload"], artifact["payload"])
        self.assertEqual(stored["confirmed_payload_hash"], artifact["payload_hash"])
        connection = connect(self.db)
        try:
            row = connection.execute("SELECT * FROM confirmations WHERE confirmation_id=?", (artifact["confirmation_id"],)).fetchone()
            self.assertEqual((row["status"], row["confirmation_method"], row["confirmation_identity"], row["confirmation_source"]), ("CONSUMED", "test_explicit_human", "employee-test", "test-harness"))
            self.assertEqual(row["payload_hash"], artifact["payload_hash"])
            self.assertIsNotNone(row["confirmed_at"])
            self.assertIsNotNone(row["consumed_at"])
        finally:
            connection.close()

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
        artifact = prepare(value, self.db)
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
        artifact = prepare(candidate(), self.db)
        artifact["payload"]["task_goal"] = "Corrected goal"
        with self.assertRaises(ConfirmationError):
            confirm(artifact, self.db, method="test_explicit_human")
        refreshed = prepare(artifact["payload"], self.db)
        confirmed = confirm(refreshed, self.db, method="test_explicit_human")
        result = commit(confirmed, self.db)
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

    def test_11_schema_v2_migrates_to_v3_and_old_data_reads(self):
        connection = connect(self.db)
        connection.executescript(MIGRATIONS[1])
        connection.execute("INSERT INTO schema_migrations VALUES (1, '2026-01-01T00:00:00Z', ?)", (digest(MIGRATIONS[1].encode()),))
        connection.executescript(MIGRATIONS[2])
        connection.execute("INSERT INTO schema_migrations VALUES (2, '2026-01-01T00:00:01Z', ?)", (digest(MIGRATIONS[2].encode()),))
        old_payload = candidate()
        old_hash = digest(old_payload)
        connection.execute(
            "INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("task_legacy", 2, old_payload["task_type"], old_payload["task_type"], old_payload["task_goal"], "adopted", json.dumps(old_payload["final_result"]), json.dumps(old_payload), old_hash, "legacy", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", "{}"),
        )
        connection.execute("INSERT INTO confirmations VALUES (?,?,?,?,?,?)", ("confirm_legacy", "task_legacy", "legacy-token-hash", old_hash, "2026-01-01T00:00:00Z", "legacy_explicit"))
        connection.commit()
        connection.close()
        connection = connect(self.db)
        migrate(connection)
        connection.close()
        self.assertEqual(show(self.db, "task_legacy")["payload"]["task_goal"], old_payload["task_goal"])
        connection = connect(self.db)
        try:
            legacy = connection.execute("SELECT status, confirmation_source, consumed_at FROM confirmations WHERE confirmation_id='confirm_legacy'").fetchone()
            self.assertEqual((legacy["status"], legacy["confirmation_source"]), ("CONSUMED", "legacy_v2"))
            self.assertIsNotNone(legacy["consumed_at"])
        finally:
            connection.close()
        artifact = prepare(candidate("new-after-migration"), self.db)
        confirmed = confirm(artifact, self.db, method="test_explicit_human")
        result = commit(confirmed, self.db)
        self.assertEqual(show(self.db, result["task_id"])["schema_version"], 3)
        connection = connect(self.db)
        try:
            self.assertEqual(current_version(connection), 3)
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
            prepare({}, self.db)
        value = candidate()
        value["steps"] = []
        with self.assertRaises(ValidationError):
            prepare(value, self.db)

    def test_unconfirmed_and_new_secret_are_blocked(self):
        artifact = prepare(candidate(), self.db)
        with self.assertRaises(ConfirmationError):
            commit(artifact, self.db)
        connection = connect(self.db)
        try:
            self.assertIsNone(connection.execute("SELECT task_id FROM tasks").fetchone())
        finally:
            connection.close()
        artifact["payload"]["steps"][0]["summary"] = "password=" + "TEST_ONLY_SECRET"
        artifact["payload_hash"] = digest(artifact["payload"])
        with self.assertRaises(ConfirmationError):
            confirm(artifact, self.db, method="test_explicit_human")

    def test_confirmation_cannot_be_consumed_twice(self):
        artifact = prepare(candidate(), self.db)
        confirmed = confirm(artifact, self.db, method="test_explicit_human")
        first = commit(confirmed, self.db)
        with self.assertRaises(ConfirmationError):
            commit(confirmed, self.db)
        connection = connect(self.db)
        try:
            row = connection.execute("SELECT status, task_id, consumed_at FROM confirmations WHERE confirmation_id=?", (confirmed["confirmation_id"],)).fetchone()
            self.assertEqual((row["status"], row["task_id"]), ("CONSUMED", first["task_id"]))
            self.assertIsNotNone(row["consumed_at"])
        finally:
            connection.close()

    def test_persistence_survives_reconnect_and_integrity_is_ok(self):
        artifact = prepare(candidate(), self.db)
        confirmed = confirm(artifact, self.db, method="test_explicit_human")
        result = commit(confirmed, self.db)
        self.assertIsNotNone(show(self.db, result["task_id"]))
        connection = connect(self.db)
        try:
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        finally:
            connection.close()

    def test_forged_internal_content_hash_is_rejected(self):
        value = candidate()
        value["evidence"][0]["content_hash"] = "b" * 64
        with self.assertRaises(ValidationError):
            prepare(value, self.db)
        self.assertFalse(self.db.exists())

    def test_external_digest_is_typed_and_not_used_as_content_hash(self):
        value = candidate()
        external_digest = "a" * 64
        value["evidence"] = [{
            "evidence_type": "file_hash", "source_ref": "approved-store:document-7",
            "external_digest": external_digest, "hash_algorithm": "sha256",
            "verification_state": "unverified", "provenance": "user_reported",
        }]
        prepared = prepare(value, self.db)
        confirmed = confirm(prepared, self.db, method="test_explicit_human")
        result = commit(confirmed, self.db)
        connection = connect(self.db)
        try:
            row = connection.execute("SELECT * FROM evidence WHERE task_id=?", (result["task_id"],)).fetchone()
            self.assertEqual((row["evidence_kind"], row["external_digest"], row["verification_state"]), ("external_reference", external_digest, "unverified"))
            self.assertNotEqual(row["content_hash"], external_digest)
            self.assertEqual(verify_evidence_chains(connection)["status"], "ok")
        finally:
            connection.close()

    def test_evidence_content_tamper_breaks_chain_verification(self):
        prepared = prepare(candidate(), self.db)
        confirmed = confirm(prepared, self.db, method="test_explicit_human")
        result = commit(confirmed, self.db)
        connection = connect(self.db)
        try:
            connection.execute("UPDATE evidence SET sanitized_excerpt='tampered' WHERE task_id=?", (result["task_id"],))
            connection.commit()
            verification = verify_evidence_chains(connection)
            self.assertEqual(verification["status"], "failed")
            self.assertEqual(len(verification["failed_event_ids"]), 1)
        finally:
            connection.close()

    def test_cli_confirmation_refuses_noninteractive_input(self):
        artifact = prepare(candidate(), self.db)
        artifact_path = Path(self.temp.name) / "confirmation.json"
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "scripts/flow_capture.py", "confirm", "--confirmation", str(artifact_path), "--db", str(self.db)],
            input=f"CONFIRM {artifact['payload_hash'][:12]}\n", text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("interactive terminal", result.stderr)
        connection = connect(self.db)
        try:
            state = connection.execute("SELECT status FROM confirmations WHERE confirmation_id=?", (artifact["confirmation_id"],)).fetchone()["status"]
            self.assertEqual(state, "PREPARED")
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
