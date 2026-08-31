import json
import sqlite3
from pathlib import Path

from . import SCHEMA_VERSION
from .errors import MigrationError
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
    row = connection.execute("SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations").fetchone()
    return row["version"]


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


def _path_signature(steps):
    return ">".join(
        f"{s['actor']}:{s['event_type']}:{digest(normalize_label(s['summary']))[:12]}"
        for s in steps
    )


def persist(connection, payload, token_hash, confirmation_method="explicit_user_confirmation"):
    migrate(connection)
    payload_hash = digest(payload)
    existing = connection.execute("SELECT task_id FROM tasks WHERE confirmed_payload_hash=?", (payload_hash,)).fetchone()
    if existing:
        return existing["task_id"], True
    now = utc_now()
    task_id, process_id, path_id = new_id("task"), new_id("process"), new_id("path")
    signature = _path_signature(payload["steps"])
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (task_id, SCHEMA_VERSION, payload["task_type"], normalize_label(payload["task_type"]), payload["task_goal"],
             payload["final_result"]["adoption_status"], canonical_json(payload["final_result"]), canonical_json(payload),
             payload_hash, signature, now, now, canonical_json(payload.get("harness_metadata", {}))),
        )
        connection.execute("INSERT INTO processes VALUES (?,?,?,?)", (process_id, task_id, payload.get("process_summary"), canonical_json(payload.get("prerequisites", []))))
        connection.execute("INSERT INTO paths VALUES (?,?,?,?)", (path_id, process_id, signature, payload["final_result"]["adoption_status"]))
        for index, step in enumerate(payload["steps"], 1):
            connection.execute("INSERT INTO steps VALUES (?,?,?,?,?,?,?,?,?)", (new_id("step"), path_id, index, step["actor"], step["event_type"], step["summary"], step["provenance"], step.get("confidence"), canonical_json(step.get("metadata", {}))))
        previous_hash = None
        for index, item in enumerate(payload.get("evidence", []), 1):
            content_hash = item.get("content_hash") or digest(item.get("sanitized_excerpt", ""))
            event_hash = digest({"task_id": task_id, "ordinal": index, "content_hash": content_hash, "previous_hash": previous_hash})
            event_id = new_id("event")
            connection.execute("INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?,?)", (event_id, task_id, index, item.get("evidence_type", "conversation_excerpt"), item.get("source_ref"), item.get("sanitized_excerpt"), content_hash, item.get("provenance", "observed"), previous_hash, event_hash, now))
            connection.execute("INSERT INTO lineage VALUES (?,?,?,?,?,?,?)", (new_id("lineage"), "process", process_id, "event", event_id, "derived_from", now))
            previous_hash = event_hash
        for ref in payload.get("external_references", []):
            connection.execute("INSERT INTO external_references VALUES (?,?,?,?,?,?)", (new_id("ref"), task_id, ref["namespace"], digest(str(ref["external_id"])), ref.get("relation", "context"), canonical_json(ref.get("metadata", {}))))
        connection.execute("INSERT INTO confirmations VALUES (?,?,?,?,?,?)", (new_id("confirm"), task_id, token_hash, payload_hash, now, confirmation_method))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return task_id, False


def read_task(connection, task_id):
    row = connection.execute("SELECT confirmed_payload_json, confirmed_payload_hash, schema_version, created_at FROM tasks WHERE task_id=?", (task_id,)).fetchone()
    if not row:
        return None
    payload = json.loads(row["confirmed_payload_json"])
    return {"task_id": task_id, "schema_version": row["schema_version"], "created_at": row["created_at"], "confirmed_payload_hash": row["confirmed_payload_hash"], "payload": payload}


def similar_tasks(connection, task_type, limit=10):
    migrate(connection)
    rows = connection.execute("SELECT task_id, task_type, adoption_status, path_signature, created_at FROM tasks WHERE task_type_normalized=? ORDER BY created_at DESC LIMIT ?", (normalize_label(task_type), limit)).fetchall()
    return [dict(row) for row in rows]
