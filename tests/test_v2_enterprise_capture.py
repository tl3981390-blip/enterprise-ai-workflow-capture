"""v2.0.0 tests: enterprise-managed capture, authorization boundaries, storage
adapter behavior, capture-persistence status separation, privacy hardening and
the Phase-2 adversarial scenarios. The v1 suite (test_workflow_capture.py) is
preserved as the personal-mode regression.

All credential-shaped fixtures are synthetic and assembled at runtime; no real
or documentation credential literals are stored in this file.
"""

import contextlib
import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from workflow_capture import SCHEMA_VERSION, service
from workflow_capture.database import MIGRATIONS, connect, migrate
from workflow_capture.errors import AuthorizationError, CaptureStorageError, ValidationError
from workflow_capture.redaction import sanitize
from workflow_capture.service import capture, commit, confirm, prepare, show, similar
from workflow_capture.util import canonical_json, digest
from workflow_capture.validation import validate_candidate

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

ENV_KEYS = (
    "WORKFLOW_CAPTURE_AUTHORIZATION_FILE",
    "WORKFLOW_CAPTURE_AUTHORIZATION_KEY",
    "WORKFLOW_CAPTURE_STORAGE",
    "WORKFLOW_CAPTURE_STORAGE_ADAPTER_MODULE",
    "WORKFLOW_CAPTURE_DB",
    "WORKFLOW_CAPTURE_FLAKY_STATE",
    "WORKFLOW_CAPTURE_FLAKY_DB",
)

# Synthetic, runtime-assembled fixtures. Never real values.
TEST_HMAC_KEY = "synthetic-test-key-" + "0" * 16
SYNTHETIC_JWT = "eyJ" + "a" * 12 + "." + "b" * 12 + "." + "c" * 8
SYNTHETIC_AWS = "AKIA" + "0" * 16
SYNTHETIC_GH = "ghp_" + "a" * 36


@contextlib.contextmanager
def capture_env(**mapping):
    backup = {key: os.environ.get(key) for key in ENV_KEYS}
    try:
        for key in ENV_KEYS:
            if key in mapping:
                if mapping[key] is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = mapping[key]
        yield
    finally:
        for key, value in backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def write_grant(directory, *, mode="ENTERPRISE_MANAGED_CAPTURE", authorized=True,
                task_types="*", departments="*", storage_adapter="local_sqlite",
                expired=False, signed_key=None):
    now = datetime.now(timezone.utc)
    grant = {
        "grant_version": 1,
        "grant_id": "grant_test_001",
        "issuer": "test-harness",
        "mode": mode,
        "capture_authorized": authorized,
        "capture_scope": {"task_types": task_types, "departments": departments},
        "storage_scope": {"adapter": storage_adapter},
        "retention_policy": "test-retention-90d",
        "issued_at": iso(now - timedelta(minutes=5)),
        "expires_at": iso(now + timedelta(hours=-1 if expired else 1)),
    }
    if signed_key is not None:
        grant["signature"] = hmac.new(
            signed_key.encode("utf-8"), canonical_json(grant).encode("utf-8"), hashlib.sha256
        ).hexdigest()
    path = Path(directory) / "grant.json"
    path.write_text(json.dumps(grant, ensure_ascii=False), encoding="utf-8")
    return str(path)


def enterprise_candidate(session="session-001", task_type="supplier-quote-comparison"):
    return {
        "capture_session_id": session,
        "task_type": task_type,
        "task_goal": "Compare three supplier quotes and produce a decision-ready summary",
        "process_summary": "Compared quotes, corrected a tax-rate misread, added a stability note.",
        "prerequisites": ["three supplier quotes", "price history access"],
        "started_at": "2026-09-01T09:00:00Z",
        "completed_at": "2026-09-01T09:24:30Z",
        "business_context": {"ref": "po-2026-0914", "department": "procurement", "workflow": "sourcing", "provenance": "harness_provided"},
        "ai_context": {"model": "example-model", "provider": "example-provider", "skill": "enterprise-ai-workflow-capture", "version": "2.0.0", "provenance": "harness_provided"},
        "steps": [
            {"actor": "human", "event_type": "action", "summary": "Uploaded three supplier quotes.", "provenance": "observed",
             "occurred_at": "2026-09-01T09:00:10Z", "duration_ms": 40000},
            {"actor": "ai", "event_type": "action", "summary": "Extracted prices, lead times and payment terms.", "provenance": "observed",
             "occurred_at": "2026-09-01T09:01:00Z", "duration_ms": 95000,
             "capability": {"kind": "model", "name": "example-model", "version": "1.2"}},
            {"actor": "human", "event_type": "correction", "summary": "Supplier B tax rate was misread; provided the verified rate.", "provenance": "observed",
             "occurred_at": "2026-09-01T09:05:00Z",
             "intervention": {"reason": "error", "rework": True, "modified_step": 2}},
            {"actor": "ai", "event_type": "retry", "summary": "Re-read supplier B quote.", "provenance": "observed", "duration_ms": 30000},
            {"actor": "tool", "event_type": "action", "summary": "Queried internal price history.", "provenance": "observed",
             "capability": {"kind": "tool", "name": "price-history-api", "version": "3"}},
            {"actor": "ai", "event_type": "decision", "summary": "Weighted criteria and ranked the offers.", "provenance": "ai_inferred", "confidence": 0.7},
            {"actor": "human", "event_type": "correction", "summary": "Added a supply-stability note to the AI draft.", "provenance": "observed",
             "intervention": {"reason": "business_preference", "rework": False}},
            {"actor": "ai", "event_type": "result", "summary": "Produced the final comparison report.", "provenance": "observed"},
        ],
        "final_result": {"summary": "Comparison report", "adoption_status": "adopted", "quality_notes": "Accepted by the requester."},
        "evidence": [{"evidence_type": "conversation_excerpt", "source_ref": "current-session:task", "sanitized_excerpt": "Supplier B tax rate was corrected before the final report.", "provenance": "observed"}],
        "external_references": [{"namespace": "erp:purchase_order", "external_id": "po-2026-0914", "relation": "subject"}],
        "harness_metadata": {"harness": "test-harness"},
    }


class EnterpriseCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / "workflow.db")
        self.grant = write_grant(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def capture_enterprise(self, candidate, **env_overrides):
        env = {"WORKFLOW_CAPTURE_AUTHORIZATION_FILE": self.grant, "WORKFLOW_CAPTURE_AUTHORIZATION_KEY": None}
        env.update(env_overrides)
        with capture_env(**env):
            return capture(candidate, self.db)

    def test_enterprise_one_shot_capture_persisted(self):
        result = self.capture_enterprise(enterprise_candidate())
        self.assertEqual(result["status"], "TASK_COMPLETED_CAPTURE_PERSISTED")
        self.assertEqual(result["capture_mode"], "ENTERPRISE_MANAGED_CAPTURE")
        self.assertTrue(result["read_back_ok"])
        self.assertFalse(result["idempotent_replay"])
        self.assertEqual(result["authorization"]["verification"], "harness_asserted_unverified")
        stored = show(self.db, result["task_id"])
        self.assertEqual(stored["capture"]["capture_status"], "TASK_COMPLETED_CAPTURE_PERSISTED")
        self.assertEqual(stored["capture"]["capture_session_id"], "session-001")
        self.assertEqual(stored["payload"]["steps"][5]["event_type"], "decision")

    def test_v2_event_fields_are_stored(self):
        result = self.capture_enterprise(enterprise_candidate())
        stored = show(self.db, result["task_id"])
        steps = stored["payload"]["steps"]
        self.assertEqual(steps[0]["occurred_at"], "2026-09-01T09:00:10Z")
        self.assertEqual(steps[0]["duration_ms"], 40000)
        self.assertEqual(steps[1]["capability"], {"kind": "model", "name": "example-model", "version": "1.2"})
        self.assertEqual(steps[2]["intervention"], {"reason": "error", "rework": True, "modified_step": 2})
        self.assertEqual(steps[6]["intervention"]["reason"], "business_preference")
        self.assertEqual(stored["capture"]["started_at"], "2026-09-01T09:00:00Z")
        self.assertEqual(stored["capture"]["completed_at"], "2026-09-01T09:24:30Z")
        context = stored["capture"]["business_context"]
        self.assertEqual(context["department"], "procurement")
        self.assertNotEqual(stored["capture"]["business_context_ref_hash"], "po-2026-0914")
        self.assertEqual(stored["capture"]["business_context_ref_hash"], digest("po-2026-0914"))
        self.assertEqual(stored["capture"]["ai_context"]["model"], "example-model")

    def test_idempotent_replay_same_session(self):
        candidate = enterprise_candidate()
        first = self.capture_enterprise(candidate)
        replay = self.capture_enterprise(candidate)
        self.assertEqual(replay["task_id"], first["task_id"])
        self.assertTrue(replay["idempotent_replay"])
        connection = connect(self.db)
        try:
            count = connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(count, 1)

    def test_same_payload_different_session_is_single_task(self):
        first = self.capture_enterprise(enterprise_candidate(session="s-1"))
        second = self.capture_enterprise(enterprise_candidate(session="s-2"))
        self.assertEqual(first["task_id"], second["task_id"])
        self.assertTrue(second["idempotent_replay"])

    def test_session_reuse_with_different_payload_is_refused(self):
        self.capture_enterprise(enterprise_candidate(session="s-9"))
        conflicting = enterprise_candidate(session="s-9")
        conflicting["task_goal"] = "A different goal under the same session"
        with self.assertRaises(Exception) as ctx:
            self.capture_enterprise(conflicting)
        self.assertIn("different payload", str(ctx.exception))

    def test_signed_grant_is_verified(self):
        grant = write_grant(self.temp.name, signed_key=TEST_HMAC_KEY)
        with capture_env(WORKFLOW_CAPTURE_AUTHORIZATION_FILE=grant, WORKFLOW_CAPTURE_AUTHORIZATION_KEY=TEST_HMAC_KEY):
            result = capture(enterprise_candidate(session="signed-1"), self.db)
        self.assertEqual(result["authorization"]["verification"], "hmac_sha256_verified")

    def test_storage_timeout_fails_honestly_then_retry_persists_once(self):
        grant = write_grant(self.temp.name, storage_adapter="enterprise_flaky")
        flaky_db = str(Path(self.temp.name) / "flaky.db")
        env = {
            "WORKFLOW_CAPTURE_AUTHORIZATION_FILE": grant,
            "WORKFLOW_CAPTURE_AUTHORIZATION_KEY": None,
            "WORKFLOW_CAPTURE_STORAGE": "enterprise_adapter",
            "WORKFLOW_CAPTURE_STORAGE_ADAPTER_MODULE": str(FIXTURES / "flaky_adapter.py"),
            "WORKFLOW_CAPTURE_FLAKY_STATE": str(Path(self.temp.name) / "flaky.marker"),
            "WORKFLOW_CAPTURE_FLAKY_DB": flaky_db,
        }
        candidate = enterprise_candidate(session="flaky-1")
        with capture_env(**env):
            with self.assertRaises(CaptureStorageError) as ctx:
                capture(candidate)
            self.assertEqual(ctx.exception.status, "TASK_COMPLETED_CAPTURE_FAILED")
            self.assertFalse(Path(flaky_db).exists())
            retried = capture(candidate)
            self.assertEqual(retried["status"], "TASK_COMPLETED_CAPTURE_PERSISTED")
            replay = capture(candidate)
            self.assertTrue(replay["idempotent_replay"])
            self.assertEqual(replay["task_id"], retried["task_id"])

    def test_wrong_read_back_never_claims_persistence(self):
        class MisreportingAdapter:
            kind = "local_sqlite"

            def persist_authorized(self, payload, record):
                return {"task_id": "task_fake", "duplicate": False, "payload_hash": digest(payload)}

            def read_task(self, task_id):
                return {"confirmed_payload_hash": "0" * 64, "schema_version": SCHEMA_VERSION, "capture": {"capture_status": "TASK_COMPLETED_CAPTURE_PERSISTED"}}

        with mock.patch.object(service, "resolve_adapter", return_value=MisreportingAdapter()):
            with self.assertRaises(CaptureStorageError) as ctx:
                self.capture_enterprise(enterprise_candidate(session="rb-1"))
        self.assertEqual(ctx.exception.status, "TASK_COMPLETED_CAPTURE_FAILED")

    def test_pending_status_is_reported_honestly(self):
        class PendingAdapter:
            kind = "local_sqlite"

            def persist_authorized(self, payload, record):
                return {"pending": True}

        with mock.patch.object(service, "resolve_adapter", return_value=PendingAdapter()):
            result = self.capture_enterprise(enterprise_candidate(session="pend-1"))
        self.assertEqual(result["status"], "TASK_COMPLETED_CAPTURE_PENDING")
        self.assertFalse(result["read_back_ok"])

    def test_adapter_internal_error_does_not_leak_details(self):
        class BrokenAdapter:
            kind = "local_sqlite"

            def persist_authorized(self, payload, record):
                raise RuntimeError("internal-driver-detail")

        with mock.patch.object(service, "resolve_adapter", return_value=BrokenAdapter()):
            with self.assertRaises(CaptureStorageError) as ctx:
                self.capture_enterprise(enterprise_candidate(session="brk-1"))
        self.assertNotIn("internal-driver-detail", str(ctx.exception))

    def test_ai_context_absent_stays_unknown(self):
        candidate = enterprise_candidate(session="noctx-1")
        del candidate["ai_context"]
        result = self.capture_enterprise(candidate)
        stored = show(self.db, result["task_id"])
        self.assertEqual(stored["capture"]["ai_context"], {})


class AuthorizationBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / "workflow.db")

    def tearDown(self):
        self.temp.cleanup()

    def attempt(self, candidate=None, **env):
        with capture_env(**env):
            return capture(candidate or enterprise_candidate(), self.db)

    def test_no_grant_fails_closed(self):
        with self.assertRaises(AuthorizationError):
            self.attempt(WORKFLOW_CAPTURE_AUTHORIZATION_FILE=None, WORKFLOW_CAPTURE_AUTHORIZATION_KEY=None)
        self.assertFalse(Path(self.db).exists())

    def test_unauthorized_grant_refused(self):
        grant = write_grant(self.temp.name, authorized=False)
        with self.assertRaises(AuthorizationError):
            self.attempt(WORKFLOW_CAPTURE_AUTHORIZATION_FILE=grant, WORKFLOW_CAPTURE_AUTHORIZATION_KEY=None)

    def test_expired_grant_refused(self):
        grant = write_grant(self.temp.name, expired=True)
        with self.assertRaises(AuthorizationError):
            self.attempt(WORKFLOW_CAPTURE_AUTHORIZATION_FILE=grant, WORKFLOW_CAPTURE_AUTHORIZATION_KEY=None)

    def test_task_type_out_of_scope_refused(self):
        grant = write_grant(self.temp.name, task_types=["contract-review"])
        with self.assertRaises(AuthorizationError) as ctx:
            self.attempt(WORKFLOW_CAPTURE_AUTHORIZATION_FILE=grant, WORKFLOW_CAPTURE_AUTHORIZATION_KEY=None)
        self.assertIn("scope", str(ctx.exception))

    def test_storage_scope_mismatch_refused(self):
        grant = write_grant(self.temp.name, storage_adapter="postgresql")
        with self.assertRaises(AuthorizationError):
            self.attempt(WORKFLOW_CAPTURE_AUTHORIZATION_FILE=grant, WORKFLOW_CAPTURE_AUTHORIZATION_KEY=None)

    def test_personal_mode_grant_does_not_enable_managed_capture(self):
        grant = write_grant(self.temp.name, mode="PERSONAL_EXPLICIT_CAPTURE")
        with self.assertRaises(AuthorizationError):
            self.attempt(WORKFLOW_CAPTURE_AUTHORIZATION_FILE=grant, WORKFLOW_CAPTURE_AUTHORIZATION_KEY=None)

    def test_missing_session_id_refused(self):
        candidate = enterprise_candidate()
        del candidate["capture_session_id"]
        grant = write_grant(self.temp.name)
        with self.assertRaises(AuthorizationError):
            self.attempt(candidate, WORKFLOW_CAPTURE_AUTHORIZATION_FILE=grant, WORKFLOW_CAPTURE_AUTHORIZATION_KEY=None)

    def test_forged_signature_refused(self):
        grant = write_grant(self.temp.name, signed_key="attacker-controlled-" + "9" * 8)
        with self.assertRaises(AuthorizationError) as ctx:
            self.attempt(WORKFLOW_CAPTURE_AUTHORIZATION_FILE=grant, WORKFLOW_CAPTURE_AUTHORIZATION_KEY=TEST_HMAC_KEY)
        self.assertIn("signature", str(ctx.exception))

    def test_signed_grant_without_configured_key_refused(self):
        grant = write_grant(self.temp.name, signed_key=TEST_HMAC_KEY)
        with self.assertRaises(AuthorizationError):
            self.attempt(WORKFLOW_CAPTURE_AUTHORIZATION_FILE=grant, WORKFLOW_CAPTURE_AUTHORIZATION_KEY=None)

    def test_unsigned_grant_with_configured_key_refused(self):
        grant = write_grant(self.temp.name)
        with self.assertRaises(AuthorizationError):
            self.attempt(WORKFLOW_CAPTURE_AUTHORIZATION_FILE=grant, WORKFLOW_CAPTURE_AUTHORIZATION_KEY=TEST_HMAC_KEY)

    def test_model_carried_authorization_claim_rejected(self):
        candidate = enterprise_candidate()
        candidate["capture_authorized"] = True
        with self.assertRaises(ValidationError):
            validate_candidate(candidate)
        candidate = enterprise_candidate()
        candidate["harness_metadata"]["authorization"] = {"capture_authorized": True}
        with self.assertRaises(ValidationError):
            validate_candidate(candidate)

    def test_grant_file_unreadable_fails_closed(self):
        with self.assertRaises(AuthorizationError):
            self.attempt(WORKFLOW_CAPTURE_AUTHORIZATION_FILE=str(Path(self.temp.name) / "missing.json"),
                         WORKFLOW_CAPTURE_AUTHORIZATION_KEY=None)

    def test_malformed_grant_fails_closed(self):
        bad = Path(self.temp.name) / "bad.json"
        bad.write_text('{"grant_id": "x"}', encoding="utf-8")
        with self.assertRaises(AuthorizationError):
            self.attempt(WORKFLOW_CAPTURE_AUTHORIZATION_FILE=str(bad), WORKFLOW_CAPTURE_AUTHORIZATION_KEY=None)

    def test_department_outside_scope_refused(self):
        grant = write_grant(self.temp.name, departments=["finance"])
        with self.assertRaises(AuthorizationError):
            self.attempt(WORKFLOW_CAPTURE_AUTHORIZATION_FILE=grant, WORKFLOW_CAPTURE_AUTHORIZATION_KEY=None)

    def test_user_reported_department_refused_in_enterprise_mode(self):
        candidate = enterprise_candidate()
        candidate["business_context"]["provenance"] = "user_reported"
        grant = write_grant(self.temp.name)
        with self.assertRaises(AuthorizationError):
            self.attempt(candidate, WORKFLOW_CAPTURE_AUTHORIZATION_FILE=grant, WORKFLOW_CAPTURE_AUTHORIZATION_KEY=None)

    def test_business_context_ref_only_is_accepted(self):
        candidate = enterprise_candidate()
        candidate["business_context"] = {"ref": "ticket-1", "provenance": "user_reported"}
        grant = write_grant(self.temp.name)
        result = self.attempt(candidate, WORKFLOW_CAPTURE_AUTHORIZATION_FILE=grant, WORKFLOW_CAPTURE_AUTHORIZATION_KEY=None)
        self.assertEqual(result["status"], "TASK_COMPLETED_CAPTURE_PERSISTED")


class ValidationAndPrivacyTests(unittest.TestCase):
    def test_employee_scoring_fields_rejected_anywhere(self):
        for key in ("employee_score", "ai_usage_score", "productivity_rank", "employee_ranking", "department_ranking"):
            candidate = enterprise_candidate()
            candidate["harness_metadata"]["extension"] = {key: 5}
            with self.assertRaises(ValidationError, msg=key):
                validate_candidate(candidate)
        candidate = enterprise_candidate()
        candidate["employee_score"] = 0.9
        with self.assertRaises(ValidationError):
            validate_candidate(candidate)

    def test_full_transcript_sized_evidence_rejected(self):
        candidate = enterprise_candidate()
        candidate["evidence"][0]["sanitized_excerpt"] = "transcript line " * 400
        with self.assertRaises(ValidationError) as ctx:
            validate_candidate(candidate)
        self.assertIn("transcript", str(ctx.exception))

    def test_oversized_process_summary_rejected(self):
        candidate = enterprise_candidate()
        candidate["process_summary"] = "x" * 5000
        with self.assertRaises(ValidationError):
            validate_candidate(candidate)

    def test_ai_inferred_requires_confidence(self):
        candidate = enterprise_candidate()
        candidate["steps"][5] = {"actor": "ai", "event_type": "decision", "summary": "Guessed the ranking.", "provenance": "ai_inferred"}
        with self.assertRaises(ValidationError):
            validate_candidate(candidate)

    def test_invalid_timing_fields_rejected(self):
        candidate = enterprise_candidate()
        candidate["steps"][0]["occurred_at"] = "not a timestamp"
        with self.assertRaises(ValidationError):
            validate_candidate(candidate)
        candidate = enterprise_candidate()
        candidate["steps"][0]["duration_ms"] = -5
        with self.assertRaises(ValidationError):
            validate_candidate(candidate)
        candidate = enterprise_candidate()
        candidate["started_at"] = "2026-13-99"
        with self.assertRaises(ValidationError):
            validate_candidate(candidate)

    def test_new_secret_shapes_are_redacted(self):
        value = {"summary": f"jwt {SYNTHETIC_JWT} aws {SYNTHETIC_AWS} gh {SYNTHETIC_GH}"}
        cleaned, findings = sanitize(value)
        self.assertNotIn(SYNTHETIC_JWT, cleaned["summary"])
        self.assertNotIn(SYNTHETIC_AWS, cleaned["summary"])
        self.assertNotIn(SYNTHETIC_GH, cleaned["summary"])
        categories = {f.category for f in findings}
        self.assertTrue({"jwt", "aws_access_key", "github_token"} <= categories)


class RuntimeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / "workflow.db")
        self.grant = write_grant(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def capture_enterprise(self, candidate):
        with capture_env(WORKFLOW_CAPTURE_AUTHORIZATION_FILE=self.grant, WORKFLOW_CAPTURE_AUTHORIZATION_KEY=None):
            return capture(candidate, self.db)

    def test_no_network_or_background_facilities_in_package(self):
        forbidden = (
            "import socket", "from socket", "import urllib", "from urllib",
            "import http", "from http", "import requests", "import subprocess",
            "from subprocess", "import asyncio", "import threading", "import ctypes",
            "import ssl", "import ftplib", "import smtplib", "import telnetlib",
        )
        package = REPO_ROOT / "workflow_capture"
        for path in package.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, text, f"{path.name} contains forbidden facility '{token}'")

    def test_no_derived_write_api_and_no_raw_overwrite_api(self):
        service_source = (REPO_ROOT / "workflow_capture" / "service.py").read_text(encoding="utf-8")
        database_source = (REPO_ROOT / "workflow_capture" / "database.py").read_text(encoding="utf-8")
        self.assertNotIn("INSERT INTO derived_knowledge", service_source + database_source)
        self.assertNotIn("UPDATE tasks", service_source + database_source)
        public = {
            name
            for name in dir(service)
            if not name.startswith("_")
            and callable(getattr(service, name))
            and getattr(getattr(service, name), "__module__", None) == "workflow_capture.service"
        }
        self.assertEqual(public, {"capture", "commit", "confirm", "load_json", "prepare", "save_json", "show", "similar"})

    def test_similar_never_declares_best_or_scores(self):
        self.capture_enterprise(enterprise_candidate(session="sim-1"))
        results = similar(self.db, "supplier-quote-comparison")
        self.assertEqual(len(results), 1)
        row = results[0]
        for banned in ("best", "score", "rank", "ranking"):
            self.assertFalse(any(banned in key.lower() for key in row), f"similar() output contains '{banned}'")

    def test_cross_task_contamination_isolated(self):
        alpha = enterprise_candidate(session="iso-a", task_type="alpha-task")
        alpha["evidence"][0]["sanitized_excerpt"] = "alpha-only-marker"
        beta = enterprise_candidate(session="iso-b", task_type="beta-task")
        beta["evidence"][0]["sanitized_excerpt"] = "beta-only-marker"
        first = self.capture_enterprise(alpha)
        second = self.capture_enterprise(beta)
        self.assertNotEqual(first["task_id"], second["task_id"])
        shown_alpha = json.dumps(show(self.db, first["task_id"]), ensure_ascii=False)
        self.assertIn("alpha-only-marker", shown_alpha)
        self.assertNotIn("beta-only-marker", shown_alpha)
        connection = connect(self.db)
        try:
            alpha_events = connection.execute("SELECT COUNT(*) FROM evidence WHERE task_id=?", (first["task_id"],)).fetchone()[0]
            total_events = connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(alpha_events, 1)
        self.assertEqual(total_events, 2)

    def test_v3_database_migrates_honestly_to_v4(self):
        connection = connect(self.db)
        for version in (1, 2, 3):
            connection.executescript(MIGRATIONS[version])
            connection.execute("INSERT INTO schema_migrations VALUES (?, '2026-01-01T00:00:00Z', ?)", (version, digest(MIGRATIONS[version].encode())))
        legacy_payload = {
            "task_type": "legacy-task", "task_goal": "Legacy goal", "steps": [
                {"actor": "human", "event_type": "action", "summary": "Legacy step.", "provenance": "observed"}
            ],
            "final_result": {"summary": "done", "adoption_status": "adopted"},
        }
        connection.execute(
            "INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("task_legacy_v3", 3, "legacy-task", "legacy-task", "Legacy goal", "adopted",
             json.dumps(legacy_payload["final_result"]), json.dumps(legacy_payload), digest(legacy_payload),
             "legacy", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", "{}"),
        )
        connection.commit()
        connection.close()
        connection = connect(self.db)
        try:
            self.assertEqual(migrate(connection), SCHEMA_VERSION)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(derived_knowledge)")}
            self.assertIn("sample_size", columns)
        finally:
            connection.close()
        stored = show(self.db, "task_legacy_v3")
        self.assertEqual(stored["payload"]["task_goal"], "Legacy goal")
        self.assertEqual(stored["capture"]["capture_mode"], "PERSONAL_EXPLICIT_CAPTURE")
        self.assertEqual(stored["capture"]["capture_status"], "TASK_COMPLETED_CAPTURE_PERSISTED")
        self.assertIsNone(stored["capture"]["capture_session_id"])
        self.assertEqual(stored["capture"]["authorization"], {})

    def test_personal_mode_still_requires_confirmation_with_v2_fields(self):
        candidate = enterprise_candidate(session="personal-1")
        artifact = prepare(candidate, self.db)
        with self.assertRaises(Exception):
            commit(artifact, self.db)
        confirmed = confirm(artifact, self.db, method="test_explicit_human")
        result = commit(confirmed, self.db)
        stored = show(self.db, result["task_id"])
        self.assertEqual(stored["capture"]["capture_mode"], "PERSONAL_EXPLICIT_CAPTURE")
        self.assertEqual(stored["capture"]["capture_session_id"], "personal-1")

    def test_provenance_cannot_be_upgraded_after_prepare(self):
        candidate = enterprise_candidate(session="prov-1")
        artifact = prepare(candidate, self.db)
        artifact["payload"]["steps"][5]["provenance"] = "observed"
        artifact["payload_hash"] = digest(artifact["payload"])
        with self.assertRaises(Exception):
            commit(artifact, self.db)


class CliIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / "cli.db")
        self.entrypoint = str(REPO_ROOT / "scripts" / "flow_capture.py")
        self.candidate_path = Path(self.temp.name) / "candidate.json"
        self.candidate_path.write_text(json.dumps(enterprise_candidate(session="cli-1")), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *cli_args, env_overrides=None):
        env = dict(os.environ)
        for key in ENV_KEYS:
            env.pop(key, None)
        if env_overrides:
            env.update(env_overrides)
        return subprocess.run(
            [sys.executable, self.entrypoint, *cli_args],
            text=True, capture_output=True, env=env, cwd=str(REPO_ROOT),
        )

    def test_capture_without_grant_exits_4(self):
        result = self.run_cli("capture", "--input", str(self.candidate_path), "--db", self.db)
        self.assertEqual(result.returncode, 4)
        self.assertIn("CAPTURE_REFUSED_UNAUTHORIZED", result.stderr)
        self.assertFalse(Path(self.db).exists())

    def test_capture_with_grant_exits_0_and_replays_idempotently(self):
        grant = write_grant(self.temp.name)
        env = {"WORKFLOW_CAPTURE_AUTHORIZATION_FILE": grant}
        first = self.run_cli("capture", "--input", str(self.candidate_path), "--db", self.db, env_overrides=env)
        self.assertEqual(first.returncode, 0, first.stderr)
        payload = json.loads(first.stdout)
        self.assertEqual(payload["status"], "TASK_COMPLETED_CAPTURE_PERSISTED")
        replay = self.run_cli("capture", "--input", str(self.candidate_path), "--db", self.db, env_overrides=env)
        self.assertEqual(replay.returncode, 0)
        self.assertTrue(json.loads(replay.stdout)["idempotent_replay"])
        shown = self.run_cli("show", "--task-id", payload["task_id"], "--db", self.db)
        self.assertEqual(shown.returncode, 0)
        self.assertEqual(json.loads(shown.stdout)["capture"]["capture_mode"], "ENTERPRISE_MANAGED_CAPTURE")

    def test_capture_storage_failure_exits_5_then_recovers(self):
        grant = write_grant(self.temp.name, storage_adapter="enterprise_flaky")
        env = {
            "WORKFLOW_CAPTURE_AUTHORIZATION_FILE": grant,
            "WORKFLOW_CAPTURE_STORAGE": "enterprise_adapter",
            "WORKFLOW_CAPTURE_STORAGE_ADAPTER_MODULE": str(FIXTURES / "flaky_adapter.py"),
            "WORKFLOW_CAPTURE_FLAKY_STATE": str(Path(self.temp.name) / "flaky.marker"),
            "WORKFLOW_CAPTURE_FLAKY_DB": str(Path(self.temp.name) / "flaky.db"),
        }
        failed = self.run_cli("capture", "--input", str(self.candidate_path), env_overrides=env)
        self.assertEqual(failed.returncode, 5)
        self.assertIn("TASK_COMPLETED_CAPTURE_FAILED", failed.stderr)
        retried = self.run_cli("capture", "--input", str(self.candidate_path), env_overrides=env)
        self.assertEqual(retried.returncode, 0, retried.stderr)
        self.assertEqual(json.loads(retried.stdout)["status"], "TASK_COMPLETED_CAPTURE_PERSISTED")

    def test_doctor_reports_authorization_surface(self):
        bare = self.run_cli("doctor")
        self.assertEqual(bare.returncode, 0, bare.stderr)
        report = json.loads(bare.stdout)
        self.assertEqual(report["package_version"], "2.0.0")
        self.assertFalse(report["authorization"]["configured"])
        grant = write_grant(self.temp.name)
        configured = self.run_cli("doctor", env_overrides={"WORKFLOW_CAPTURE_AUTHORIZATION_FILE": grant})
        self.assertEqual(configured.returncode, 0, configured.stderr)
        auth = json.loads(configured.stdout)["authorization"]
        self.assertTrue(auth["configured"])
        self.assertEqual(auth["mode"], "ENTERPRISE_MANAGED_CAPTURE")


if __name__ == "__main__":
    unittest.main()
