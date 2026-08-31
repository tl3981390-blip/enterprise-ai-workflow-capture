import json
import sqlite3
from pathlib import Path

from . import SCHEMA_VERSION
from .errors import ConfirmationError, MigrationError
from .util import canonical_json, digest, new_id, normalize_label, utc_now


MIGRATIONS = {
    1: """
CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, checksum TEXT NOT NULL);
CREATE TABLE tasks(
  task_id TEXT PRIMARY KEY, schema_version INTEGER NOT NULL, task_type TEXT NOT NULL,
  task_type_normalized TEXT NOT NULL, task_goal TEXT NOT NULL, adoption_status TEXT NOT NULL,
  final_result_json TEXT NOT NULL, confirmed_payload_json TEXT NOT NULL,
  confirmed_payload_hash TEXT NOT NULL UNIQUE, path_signature TEXT NOT NULL,
  created_at TEXT NOT NULL, confirmed_at TEXT NOT NULL, harness_metadata_json TEXT NOT NULL
);
CREATE INDEX idx_tasks_type_created ON tasks(task_type_normalized, created_at DESC);
CREATE TABLE processes(process_id TEXT PRIMARY KEY, task_id TEXT NOT NULL UNIQUE REFERENCES tasks(task_id), summary TEXT, prerequisites_json TEXT NOT NULL);
CREATE TABLE paths(path_id TEXT PRIMARY KEY, process_id TEXT NOT NULL REFERENCES processes(process_id), signature TEXT NOT NULL, outcome TEXT NOT NULL);
CREATE TABLE steps(step_id TEXT PRIMARY KEY, path_id TEXT NOT NULL REFERENCES paths(path_id), ordinal INTEGER NOT NULL, actor TEXT NOT NULL, event_type TEXT NOT NULL, summary TEXT NOT NULL, provenance TEXT NOT NULL, confidence REAL, metadata_json TEXT NOT NULL, UNIQUE(path_id, ordinal));
CREATE TABLE evidence(event_id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(task_id), ordinal INTEGER NOT NULL, evidence_type TEXT NOT NULL, source_ref TEXT, sanitized_excerpt TEXT, content_hash TEXT NOT NULL, provenance TEXT NOT NULL, previous_hash TEXT, event_hash TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, UNIQUE(task_id, ordinal));
CREATE TABLE lineage(lineage_id TEXT PRIMARY KEY, derived_kind TEXT NOT NULL, derived_id TEXT NOT NULL, source_kind TEXT NOT NULL, source_id TEXT NOT NULL, relation TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE external_references(reference_id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(task_id), namespace TEXT NOT NULL, external_id_hash TEXT NOT NULL, relation TEXT NOT NULL, metadata_json TEXT NOT NULL);
CREATE TABLE confirmations(confirmation_id TEXT PRIMARY KEY, task_id TEXT NOT NULL UNIQUE REFERENCES tasks(task_id), confirmation_token_hash TEXT NOT NULL, confirmed_payload_hash TEXT NOT NULL, confirmed_at TEXT NOT NULL, confirmation_method TEXT NOT NULL);
""",
    2: """
CREATE TABLE derived_knowledge(
  knowledge_id TEXT PRIMARY KEY, knowledge_type TEXT NOT NULL,
  task_type_normalized TEXT NOT NULL, claim_json TEXT NOT NULL,
  confidence REAL NOT NULL, status TEXT NOT NULL,
  method_version TEXT NOT NULL, created_at TEXT NOT NULL, supersedes_id TEXT
);
CREATE INDEX idx_knowledge_type ON derived_knowledge(knowledge_type, task_type_normalized, created_at DESC);
""",
    3: """
ALTER TABLE confirmations RENAME TO confirmations_v2;
CREATE TABLE confirmations(
  confirmation_id TEXT PRIMARY KEY,
  task_id TEXT UNIQUE REFERENCES tasks(task_id),
  payload_json TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  prepared_at TEXT NOT NULL,
  confirmed_at TEXT,
  confirmation_method TEXT,
  confirmation_identity TEXT,
  confirmation_source TEXT,
  status TEXT NOT NULL CHECK(status IN ('PREPARED','CONFIRMED','CONSUMED')),
  consumed_at TEXT,
  CHECK(confirmation_identity IS NULL OR confirmation_source IS NOT NULL),
  CHECK((status='PREPARED' AND confirmed_at IS NULL AND consumed_at IS NULL AND task_id IS NULL)
     OR (status='CONFIRMED' AND confirmed_at IS NOT NULL AND length(confirmation_method)>0 AND consumed_at IS NULL AND task_id IS NULL)
     OR (status='CONSUMED' AND confirmed_at IS NOT NULL AND length(confirmation_method)>0 AND consumed_at IS NOT NULL AND task_id IS NOT NULL))
);
INSERT INTO confirmations(
  confirmation_id, task_id, payload_json, payload_hash, prepared_at, confirmed_at,
  confirmation_method, confirmation_identity, confirmation_source, status, consumed_at
)
SELECT c.confirmation_id, c.task_id, t.confirmed_payload_json, c.confirmed_payload_hash,
       c.confirmed_at, c.confirmed_at, c.confirmation_method, NULL, 'legacy_v2', 'CONSUMED', c.confirmed_at
FROM confirmations_v2 c JOIN tasks t ON t.task_id=c.task_id;
DROP TABLE confirmations_v2;
CREATE INDEX idx_confirmations_status ON confirmations(status, prepared_at);
ALTER TABLE evidence ADD COLUMN evidence_kind TEXT NOT NULL DEFAULT 'legacy';
ALTER TABLE evidence ADD COLUMN hash_algorithm TEXT NOT NULL DEFAULT 'sha256';
ALTER TABLE evidence ADD COLUMN external_digest TEXT;
ALTER TABLE evidence ADD COLUMN verification_state TEXT NOT NULL DEFAULT 'legacy_unverified';
""",
}


def connect(path):
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    return connection


def current_version(connection):
    exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone()
    if not exists:
        return 0
    return connection.execute("SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations").fetchone()["version"]


def migrate(connection, target=SCHEMA_VERSION):
    current = current_version(connection)
    if current > target:
        raise MigrationError(f"database schema {current} is newer than supported schema {target}")
    for version in range(current + 1, target + 1):
        sql = MIGRATIONS.get(version)
        if not sql:
            raise MigrationError(f"missing migration {version}")
        try:
            connection.executescript("BEGIN IMMEDIATE;\n" + sql)
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at, checksum) VALUES (?, ?, ?)",
                (version, utc_now(), digest(sql.encode("utf-8"))),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return current_version(connection)


def create_confirmation(connection, payload):
    migrate(connection)
    confirmation_id = new_id("confirm")
    payload_hash = digest(payload)
    prepared_at = utc_now()
    connection.execute(
        "INSERT INTO confirmations(confirmation_id,payload_json,payload_hash,prepared_at,status) VALUES (?,?,?,?, 'PREPARED')",
        (confirmation_id, canonical_json(payload), payload_hash, prepared_at),
    )
    connection.commit()
    return confirmation_id, payload_hash, prepared_at


def read_confirmation(connection, confirmation_id):
    row = connection.execute("SELECT * FROM confirmations WHERE confirmation_id=?", (confirmation_id,)).fetchone()
    return dict(row) if row else None


def confirm_confirmation(connection, confirmation_id, expected_payload_hash, method, identity=None, source=None):
    migrate(connection)
    if not str(method).strip():
        raise ConfirmationError("confirmation method is required")
    if bool(identity) != bool(source):
        raise ConfirmationError("confirmation identity and source must be supplied together")
    now = utc_now()
    cursor = connection.execute(
        """UPDATE confirmations
           SET status='CONFIRMED', confirmed_at=?, confirmation_method=?, confirmation_identity=?, confirmation_source=?
           WHERE confirmation_id=? AND status='PREPARED' AND payload_hash=?""",
        (now, method, identity, source, confirmation_id, expected_payload_hash),
    )
    if cursor.rowcount != 1:
        connection.rollback()
        raise ConfirmationError("confirmation is missing, changed, or no longer PREPARED")
    connection.commit()
    return read_confirmation(connection, confirmation_id)


def _path_signature(steps):
    return ">".join(f"{s['actor']}:{s['event_type']}:{digest(normalize_label(s['summary']))[:12]}" for s in steps)


def _canonical_evidence(item):
    common = {
        "evidence_type": item.get("evidence_type", "conversation_excerpt"),
        "source_ref": item.get("source_ref"),
        "provenance": item.get("provenance", "observed"),
    }
    if item.get("sanitized_excerpt"):
        content = {**common, "sanitized_excerpt": item["sanitized_excerpt"]}
        return "internal", "sha256", None, "internally_verified", digest(content)
    content = {
        **common,
        "external_digest": item["external_digest"].lower(),
        "hash_algorithm": item["hash_algorithm"],
        "verification_state": item["verification_state"],
    }
    return "external_reference", item["hash_algorithm"], item["external_digest"].lower(), item["verification_state"], digest(content)


def _insert_task(connection, payload, payload_hash, confirmed_at):
    existing = connection.execute("SELECT task_id FROM tasks WHERE confirmed_payload_hash=?", (payload_hash,)).fetchone()
    if existing:
        return existing["task_id"], True
    now = utc_now()
    task_id, process_id, path_id = new_id("task"), new_id("process"), new_id("path")
    signature = _path_signature(payload["steps"])
    connection.execute(
        "INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (task_id, SCHEMA_VERSION, payload["task_type"], normalize_label(payload["task_type"]), payload["task_goal"],
         payload["final_result"]["adoption_status"], canonical_json(payload["final_result"]), canonical_json(payload),
         payload_hash, signature, now, confirmed_at, canonical_json(payload.get("harness_metadata", {}))),
    )
    connection.execute("INSERT INTO processes VALUES (?,?,?,?)", (process_id, task_id, payload.get("process_summary"), canonical_json(payload.get("prerequisites", []))))
    connection.execute("INSERT INTO paths VALUES (?,?,?,?)", (path_id, process_id, signature, payload["final_result"]["adoption_status"]))
    for index, step in enumerate(payload["steps"], 1):
        connection.execute("INSERT INTO steps VALUES (?,?,?,?,?,?,?,?,?)", (new_id("step"), path_id, index, step["actor"], step["event_type"], step["summary"], step["provenance"], step.get("confidence"), canonical_json(step.get("metadata", {}))))
    previous_hash = None
    for index, item in enumerate(payload.get("evidence", []), 1):
        kind, algorithm, external_digest, verification_state, content_hash = _canonical_evidence(item)
        event_hash = digest({
            "task_id": task_id, "ordinal": index, "evidence_kind": kind,
            "content_hash": content_hash, "hash_algorithm": "sha256",
            "verification_state": verification_state, "previous_hash": previous_hash,
        })
        event_id = new_id("event")
        connection.execute(
            """INSERT INTO evidence(
                 event_id,task_id,ordinal,evidence_type,source_ref,sanitized_excerpt,content_hash,
                 provenance,previous_hash,event_hash,created_at,evidence_kind,hash_algorithm,
                 external_digest,verification_state) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (event_id, task_id, index, item.get("evidence_type", "conversation_excerpt"), item.get("source_ref"),
             item.get("sanitized_excerpt"), content_hash, item.get("provenance", "observed"), previous_hash,
             event_hash, now, kind, algorithm, external_digest, verification_state),
        )
        connection.execute("INSERT INTO lineage VALUES (?,?,?,?,?,?,?)", (new_id("lineage"), "process", process_id, "event", event_id, "derived_from", now))
        previous_hash = event_hash
    for ref in payload.get("external_references", []):
        connection.execute("INSERT INTO external_references VALUES (?,?,?,?,?,?)", (new_id("ref"), task_id, ref["namespace"], digest(str(ref["external_id"])), ref.get("relation", "context"), canonical_json(ref.get("metadata", {}))))
    return task_id, False


def persist_confirmed(connection, confirmation_id, expected_payload_hash):
    migrate(connection)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM confirmations WHERE confirmation_id=? AND status='CONFIRMED' AND consumed_at IS NULL AND payload_hash=?",
            (confirmation_id, expected_payload_hash),
        ).fetchone()
        if not row:
            raise ConfirmationError("confirmation has not occurred, changed, or was already consumed")
        payload = json.loads(row["payload_json"])
        task_id, duplicate = _insert_task(connection, payload, row["payload_hash"], row["confirmed_at"])
        consumed_at = utc_now()
        cursor = connection.execute(
            "UPDATE confirmations SET status='CONSUMED', consumed_at=?, task_id=? WHERE confirmation_id=? AND status='CONFIRMED' AND consumed_at IS NULL",
            (consumed_at, task_id, confirmation_id),
        )
        if cursor.rowcount != 1:
            raise ConfirmationError("confirmation was consumed concurrently")
        connection.commit()
        return task_id, duplicate
    except Exception:
        connection.rollback()
        raise


def read_task(connection, task_id):
    row = connection.execute("SELECT confirmed_payload_json, confirmed_payload_hash, schema_version, created_at FROM tasks WHERE task_id=?", (task_id,)).fetchone()
    if not row:
        return None
    return {"task_id": task_id, "schema_version": row["schema_version"], "created_at": row["created_at"], "confirmed_payload_hash": row["confirmed_payload_hash"], "payload": json.loads(row["confirmed_payload_json"])}


def similar_tasks(connection, task_type, limit=10):
    migrate(connection)
    rows = connection.execute("SELECT task_id, task_type, adoption_status, path_signature, created_at FROM tasks WHERE task_type_normalized=? ORDER BY created_at DESC LIMIT ?", (normalize_label(task_type), limit)).fetchall()
    return [dict(row) for row in rows]


def verify_evidence_chains(connection):
    migrate(connection)
    failures = []
    legacy_unverified = 0
    task_ids = [row["task_id"] for row in connection.execute("SELECT DISTINCT task_id FROM evidence ORDER BY task_id")]
    checked = 0
    for task_id in task_ids:
        previous_hash = None
        rows = connection.execute("SELECT * FROM evidence WHERE task_id=? ORDER BY ordinal", (task_id,)).fetchall()
        for row in rows:
            if row["verification_state"] == "legacy_unverified":
                legacy_unverified += 1
                previous_hash = row["event_hash"]
                continue
            item = {
                "evidence_type": row["evidence_type"], "source_ref": row["source_ref"],
                "sanitized_excerpt": row["sanitized_excerpt"], "provenance": row["provenance"],
                "external_digest": row["external_digest"], "hash_algorithm": row["hash_algorithm"],
                "verification_state": row["verification_state"],
            }
            _, _, _, verification_state, expected_content_hash = _canonical_evidence(item)
            expected_event_hash = digest({
                "task_id": task_id, "ordinal": row["ordinal"], "evidence_kind": row["evidence_kind"],
                "content_hash": expected_content_hash, "hash_algorithm": "sha256",
                "verification_state": verification_state, "previous_hash": previous_hash,
            })
            if row["content_hash"] != expected_content_hash or row["previous_hash"] != previous_hash or row["event_hash"] != expected_event_hash:
                failures.append(row["event_id"])
            previous_hash = row["event_hash"]
            checked += 1
    return {"status": "ok" if not failures else "failed", "checked_events": checked, "legacy_unverified_events": legacy_unverified, "failed_event_ids": failures}
