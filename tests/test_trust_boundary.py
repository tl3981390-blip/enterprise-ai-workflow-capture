"""TRUST boundary attack tests (v2.0.1).

Every scenario tries to obtain enterprise authority or harness-owned context
without a genuinely verified harness assertion. Keys are generated in memory at
test runtime; no key material is stored in this file.
"""

import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from workflow_capture.authorization import (
    TRUST_CLASS_DEVELOPMENT,
    TRUST_CLASS_PRODUCTION,
    VerifiedHarnessCaptureContext,
)
from workflow_capture.errors import AuthorizationError, ValidationError
from workflow_capture.service import capture, show
from workflow_capture.util import canonical_json
from workflow_capture.validation import validate_candidate, validate_enterprise_untrusted

REPO_ROOT = Path(__file__).resolve().parents[1]

ENV_KEYS = (
    "WORKFLOW_CAPTURE_AUTHORIZATION_FILE",
    "WORKFLOW_CAPTURE_AUTHORIZATION_KEY",
    "WORKFLOW_CAPTURE_STORAGE",
    "WORKFLOW_CAPTURE_STORAGE_ADAPTER_MODULE",
    "WORKFLOW_CAPTURE_DB",
    "WORKFLOW_CAPTURE_ASSERTION",
    "WORKFLOW_CAPTURE_TRUST_ROOT",
    "WORKFLOW_CAPTURE_MODE",
)


class trust_env:
    def __init__(self, **mapping):
        self.mapping = mapping
        self.backup = {}

    def __enter__(self):
        for key in ENV_KEYS:
            self.backup[key] = os.environ.get(key)
            if key in self.mapping:
                if self.mapping[key] is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = self.mapping[key]
        return self

    def __exit__(self, *exc):
        for key, value in self.backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def make_keypair():
    private = Ed25519PrivateKey.generate()
    public_b64 = base64.b64encode(private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode("ascii")
    return private, public_b64


def write_trust_root(directory, issuers, trust_class=TRUST_CLASS_PRODUCTION):
    path = Path(directory) / "trust-root.json"
    path.write_text(json.dumps({
        "trust_root_version": 1,
        "trust_class": trust_class,
        "trusted_issuers": issuers,
    }, ensure_ascii=False), encoding="utf-8")
    return str(path)


def build_assertion(*, issuer="enterprise-harness", session="asserted-session-001",
                    task_types=None, departments=None, storage_adapter="local_sqlite",
                    business_context=None, expired=False):
    now = datetime.now(timezone.utc)
    return {
        "assertion_version": 1,
        "assertion_id": "assertion-test-0001",
        "issuer": issuer,
        "key_id": "ent-key-1",
        "capture_authorized": True,
        "mode": "ENTERPRISE_MANAGED_CAPTURE",
        "capture_session_id": session,
        "capture_scope": {"task_types": task_types or ["supplier-quote-comparison"],
                          "departments": departments or ["procurement"]},
        "storage_scope": {"adapter": storage_adapter},
        "business_context": business_context or {},
        "retention_policy": "ent-retention-1y",
        "issued_at": iso(now - timedelta(minutes=2)),
        "expires_at": iso(now + timedelta(hours=-1 if expired else 1)),
        "nonce": "nonce-" + base64.urlsafe_b64encode(os.urandom(9)).decode(),
    }


def sign_assertion(private_key, assertion):
    signed = {k: v for k, v in assertion.items() if k != "signature"}
    assertion["signature"] = base64.b64encode(private_key.sign(canonical_json(signed).encode("utf-8"))).decode("ascii")
    return assertion


def write_assertion(directory, assertion):
    path = Path(directory) / "assertion.json"
    path.write_text(json.dumps(assertion, ensure_ascii=False), encoding="utf-8")
    return str(path)


def production_candidate(task_type="supplier-quote-comparison"):
    """Untrusted enterprise candidate: task facts only. No session id, no
    harness-owned context, no authorization claims."""
    return {
        "task_type": task_type,
        "task_goal": "Compare three supplier quotes and produce a decision-ready summary",
        "process_summary": "Compared quotes, corrected a tax-rate misread, added a stability note.",
        "prerequisites": ["three supplier quotes"],
        "started_at": "2026-09-01T09:00:00Z",
        "completed_at": "2026-09-01T09:24:30Z",
        "steps": [
            {"actor": "human", "event_type": "action", "summary": "Uploaded three supplier quotes.", "provenance": "observed"},
            {"actor": "ai", "event_type": "action", "summary": "Extracted prices and terms.", "provenance": "observed"},
            {"actor": "human", "event_type": "correction", "summary": "Corrected supplier B tax rate.", "provenance": "observed",
             "intervention": {"reason": "error", "rework": True, "modified_step": 2}},
            {"actor": "ai", "event_type": "result", "summary": "Produced the final report.", "provenance": "observed"},
        ],
        "final_result": {"summary": "Comparison report", "adoption_status": "adopted"},
        "evidence": [{"evidence_type": "conversation_excerpt", "source_ref": "current-session:task",
                      "sanitized_excerpt": "Supplier B tax rate was corrected.", "provenance": "observed"}],
        "harness_metadata": {"harness": "test-harness"},
    }


class TrustBoundaryBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / "workflow.db")
        self.enterprise_key, self.enterprise_public_b64 = make_keypair()
        self.trust_root = write_trust_root(
            self.temp.name,
            {"enterprise-harness": {"algorithm": "Ed25519", "key_id": "ent-key-1", "public_key": self.enterprise_public_b64}},
        )

    def tearDown(self):
        self.temp.cleanup()

    def valid_assertion_path(self, **overrides):
        assertion = build_assertion(**overrides)
        return write_assertion(self.temp.name, sign_assertion(self.enterprise_key, assertion))

    def attempt(self, candidate=None, **env):
        with trust_env(**env):
            return capture(candidate or production_candidate(), self.db)

    def attempt_with_assertion(self, assertion_path, candidate=None, **env):
        return self.attempt(candidate,
                            WORKFLOW_CAPTURE_ASSERTION=assertion_path,
                            WORKFLOW_CAPTURE_TRUST_ROOT=self.trust_root,
                            WORKFLOW_CAPTURE_AUTHORIZATION_FILE=None,
                            WORKFLOW_CAPTURE_AUTHORIZATION_KEY=None,
                            WORKFLOW_CAPTURE_MODE=None,
                            **env)


class TrustAttackTests(TrustBoundaryBase):
    def test_trust001_forged_unsigned_assertion_fails(self):
        forged = build_assertion()
        forged_path = write_assertion(self.temp.name, forged)  # no signature at all
        with self.assertRaises(AuthorizationError):
            self.attempt_with_assertion(forged_path)
        forged["signature"] = base64.b64encode(b"not-a-real-signature").decode()
        with self.assertRaises(AuthorizationError):
            self.attempt_with_assertion(write_assertion(self.temp.name, forged))
        self.assertFalse(Path(self.db).exists())

    def test_trust002_model_points_env_at_own_assertion_fails(self):
        model_key, _ = make_keypair()
        assertion = sign_assertion(model_key, build_assertion(issuer="enterprise-harness"))
        with self.assertRaises(AuthorizationError):
            self.attempt_with_assertion(write_assertion(self.temp.name, assertion))
        model_issuer = sign_assertion(model_key, build_assertion(issuer="model-self-issuer"))
        with self.assertRaises(AuthorizationError) as ctx:
            self.attempt_with_assertion(write_assertion(self.temp.name, model_issuer))
        self.assertIn("trusted", str(ctx.exception))

    def test_trust003_model_cannot_select_trust_root_or_keys(self):
        candidate = production_candidate()
        for key in ("trust_root", "public_key", "verifier", "issuer", "assertion_id", "signature"):
            forged = dict(candidate)
            forged["harness_metadata"] = {"extension": {key: "model-chosen"}}
            with self.assertRaises(ValidationError, msg=key):
                validate_candidate(forged)
        model_key, model_public = make_keypair()
        assertion = sign_assertion(model_key, build_assertion())
        with self.assertRaises(AuthorizationError):
            self.attempt_with_assertion(write_assertion(self.temp.name, assertion))
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "flow_capture.py"), "capture",
             "--input", "x.json", "--trust-root", "model-controlled.json"],
            text=True, capture_output=True, cwd=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments", result.stderr)
        self.assertTrue(model_public)

    def test_trust004_legacy_hmac_signer_cannot_authorize_production(self):
        grant_proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "make_test_grant.py"),
             "--output", str(Path(self.temp.name) / "grant.json"),
             "--grant-id", "grant_model_self", "--issuer", "model-self",
             "--storage-adapter", "local_sqlite"],
            text=True, capture_output=True,
            env={**os.environ, "WORKFLOW_CAPTURE_AUTHORIZATION_KEY": "model-chosen-" + "7" * 8},
        )
        self.assertEqual(grant_proc.returncode, 0, grant_proc.stderr)
        self.assertIn("DEVELOPMENT_TEST_ONLY", grant_proc.stderr)
        candidate = dict(production_candidate())
        candidate["capture_session_id"] = "model-session"
        with self.assertRaises(AuthorizationError):
            self.attempt(candidate,
                         WORKFLOW_CAPTURE_AUTHORIZATION_FILE=str(Path(self.temp.name) / "grant.json"),
                         WORKFLOW_CAPTURE_AUTHORIZATION_KEY="model-chosen-" + "7" * 8,
                         WORKFLOW_CAPTURE_MODE="PRODUCTION_ENTERPRISE",
                         WORKFLOW_CAPTURE_ASSERTION=None,
                         WORKFLOW_CAPTURE_TRUST_ROOT=None)
        with self.assertRaises(ValidationError):
            validate_enterprise_untrusted(candidate)

    def test_trust005_forged_capture_session_id_fails(self):
        candidate = production_candidate()
        candidate["capture_session_id"] = "model-forged-session"
        with self.assertRaises(ValidationError):
            self.attempt_with_assertion(self.valid_assertion_path(), candidate)
        self.assertFalse(Path(self.db).exists())

    def test_trust006_session_mismatch_fails(self):
        candidate = production_candidate()
        candidate["capture_session_id"] = "session-B"
        with self.assertRaises(ValidationError):
            self.attempt_with_assertion(self.valid_assertion_path(session="session-A"), candidate)

    def test_trust007_fake_harness_provided_department_fails(self):
        candidate = production_candidate()
        candidate["business_context"] = {"department": "procurement", "provenance": "harness_provided"}
        with self.assertRaises(ValidationError):
            self.attempt_with_assertion(self.valid_assertion_path(), candidate)

    def test_trust008_context_mismatch_fails(self):
        candidate = production_candidate()
        candidate["business_context"] = {"department": "procurement", "provenance": "user_reported"}
        assertion_path = self.valid_assertion_path(
            business_context={"department": "finance", "workflow": "sourcing"},
            departments=["finance"],
        )
        with self.assertRaises(ValidationError):
            self.attempt_with_assertion(assertion_path, candidate)

    def test_trust009_scope_mismatch_fails(self):
        with self.assertRaises(AuthorizationError) as ctx:
            self.attempt_with_assertion(self.valid_assertion_path(), production_candidate(task_type="contract-review"))
        self.assertIn("scope", str(ctx.exception))

    def test_trust010_expired_assertion_fails(self):
        with self.assertRaises(AuthorizationError) as ctx:
            self.attempt_with_assertion(self.valid_assertion_path(expired=True))
        self.assertIn("expired", str(ctx.exception))

    def test_trust011_tampered_assertion_fails(self):
        tamperings = [
            ("scope", lambda a: a["capture_scope"].update({"task_types": ["*"]})),
            ("department", lambda a: a.update({"business_context": {"department": "finance"}})),
            ("session", lambda a: a.update({"capture_session_id": "other-session"})),
            ("storage", lambda a: a["storage_scope"].update({"adapter": "other_store"})),
            ("retention", lambda a: a.update({"retention_policy": "keep-forever"})),
        ]
        for name, tamper in tamperings:
            with self.subTest(tampered_field=name):
                assertion = sign_assertion(self.enterprise_key, build_assertion())
                tamper(assertion)
                with self.assertRaises(AuthorizationError):
                    self.attempt_with_assertion(write_assertion(self.temp.name, assertion))

    def test_trust012_real_trusted_assertion_passes(self):
        assertion_path = self.valid_assertion_path(
            business_context={"department": "procurement", "workflow": "sourcing", "business_context_ref": "po-2026-0914"},
        )
        result = self.attempt_with_assertion(assertion_path)
        self.assertEqual(result["status"], "TASK_COMPLETED_CAPTURE_PERSISTED")
        self.assertEqual(result["trust_class"], TRUST_CLASS_PRODUCTION)
        self.assertEqual(result["authorization"]["verification"], "asymmetric_signature_verified")
        self.assertEqual(result["authorization"]["assertion_id"], "assertion-test-0001")
        self.assertEqual(result["capture_session_id"], "asserted-session-001")
        record_json = json.dumps(result["authorization"])
        self.assertNotIn('"signature":', record_json)
        self.assertNotIn('"public_key":', record_json)
        stored = show(self.db, result["task_id"])
        self.assertEqual(stored["capture"]["capture_session_id"], "asserted-session-001")
        context = stored["capture"]["business_context"]
        self.assertEqual(context["provenance"], "harness_provided")
        self.assertEqual(context["department"], "procurement")
        self.assertEqual(context["workflow"], "sourcing")
        replay = self.attempt_with_assertion(assertion_path)
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(replay["task_id"], result["task_id"])

    def test_trust013_no_production_signer_or_private_key_in_asset(self):
        package = REPO_ROOT / "workflow_capture"
        for path in package.rglob("*.py"):
            self.assertNotIn("Ed25519PrivateKey", path.read_text(encoding="utf-8"),
                             f"runtime module {path.name} contains signing capability")
        scripts = list((REPO_ROOT / "scripts").glob("*.py"))
        signing_scripts = [p.name for p in scripts if "Ed25519PrivateKey" in p.read_text(encoding="utf-8")]
        self.assertEqual(signing_scripts, ["make_test_assertion.py"])
        pem_block = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]{100,}?-----END")
        for path in list(package.rglob("*.py")) + scripts:
            # redaction.py contains only the detector regex source, never a key body
            self.assertIsNone(pem_block.search(path.read_text(encoding="utf-8")),
                              f"{path.name} contains a real private key block")
        refusal = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "make_test_assertion.py"),
             "--trust-root", str(Path(self.temp.name) / "tr.json"),
             "--assertion", str(Path(self.temp.name) / "as.json"),
             "--issuer", "x", "--session", "s", "--trust-class", TRUST_CLASS_PRODUCTION],
            text=True, capture_output=True,
        )
        self.assertNotEqual(refusal.returncode, 0)


class TrustModeTests(TrustBoundaryBase):
    def test_production_mode_rejects_development_trust_root(self):
        key, public_b64 = make_keypair()
        dev_root = write_trust_root(
            self.temp.name,
            {"enterprise-harness": {"algorithm": "Ed25519", "key_id": "ent-key-1", "public_key": public_b64}},
            trust_class=TRUST_CLASS_DEVELOPMENT,
        )
        assertion_path = write_assertion(self.temp.name, sign_assertion(key, build_assertion()))
        with self.assertRaises(AuthorizationError):
            self.attempt_with_assertion_env(assertion_path, dev_root, mode="PRODUCTION_ENTERPRISE")

    def test_development_mode_rejects_production_trust_root(self):
        assertion_path = self.valid_assertion_path()
        with self.assertRaises(AuthorizationError):
            self.attempt_with_assertion_env(assertion_path, self.trust_root, mode="DEVELOPMENT_TEST")

    def test_development_assertion_path_is_marked_test_only(self):
        key, public_b64 = make_keypair()
        dev_root = write_trust_root(
            self.temp.name,
            {"enterprise-harness": {"algorithm": "Ed25519", "key_id": "ent-key-1", "public_key": public_b64}},
            trust_class=TRUST_CLASS_DEVELOPMENT,
        )
        assertion_path = write_assertion(self.temp.name, sign_assertion(key, build_assertion()))
        result = self.attempt_with_assertion_env(assertion_path, dev_root)
        self.assertEqual(result["status"], "TASK_COMPLETED_CAPTURE_PERSISTED")
        self.assertEqual(result["trust_class"], TRUST_CLASS_DEVELOPMENT)

    def test_assertion_configured_without_trust_root_fails_closed(self):
        with self.assertRaises(AuthorizationError):
            self.attempt(WORKFLOW_CAPTURE_ASSERTION=self.valid_assertion_path(),
                         WORKFLOW_CAPTURE_TRUST_ROOT=None,
                         WORKFLOW_CAPTURE_AUTHORIZATION_FILE=None,
                         WORKFLOW_CAPTURE_AUTHORIZATION_KEY=None,
                         WORKFLOW_CAPTURE_MODE=None)

    def test_context_object_cannot_be_constructed_outside_verifier(self):
        with self.assertRaises(AuthorizationError):
            VerifiedHarnessCaptureContext(None, assertion={}, trust_class=TRUST_CLASS_PRODUCTION,
                                          verification_method="asymmetric_signature_verified")

    def attempt_with_assertion_env(self, assertion_path, trust_root, mode=None):
        return self.attempt(None,
                            WORKFLOW_CAPTURE_ASSERTION=assertion_path,
                            WORKFLOW_CAPTURE_TRUST_ROOT=trust_root,
                            WORKFLOW_CAPTURE_AUTHORIZATION_FILE=None,
                            WORKFLOW_CAPTURE_AUTHORIZATION_KEY=None,
                            WORKFLOW_CAPTURE_MODE=mode)


if __name__ == "__main__":
    unittest.main()
