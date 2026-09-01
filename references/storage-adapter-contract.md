# Storage Adapter Contract

The Skill defines a storage boundary; it does not build an enterprise database platform.

## Kinds

| Kind | Selection | Provided by |
|---|---|---|
| `local_sqlite` | default, or `--db <path>` | this repository (reference implementation) |
| `enterprise_adapter` | `WORKFLOW_CAPTURE_STORAGE=enterprise_adapter` + `WORKFLOW_CAPTURE_STORAGE_ADAPTER_MODULE` | the enterprise at deployment (PostgreSQL, internal API, approved database service, …) |

The enterprise adapter module (dotted module path or `.py` file path) must expose `create_adapter()` returning an adapter object. Storage credentials are read by that module from its own environment or key service — never from this repository, a candidate payload, or a CLI flag. An explicit `--db` always selects `local_sqlite`.

## Contract

An adapter declares `kind` and implements:

| Method | Semantics |
|---|---|
| `health()` | Adapter health dict; never raises raw driver errors. |
| `ensure_schema()` | Migrate to the supported schema; returns the schema version. |
| `create_confirmation(payload)` | Store a `PREPARED` confirmation intent; returns `(confirmation_id, payload_hash, prepared_at)`. `payload_hash` is the content hash (`capture_session_id` excluded). |
| `read_confirmation(confirmation_id)` | Dict or `None`. |
| `confirm_confirmation(confirmation_id, expected_payload_hash, method, identity, source)` | Atomically transition `PREPARED → CONFIRMED` for the exact payload hash; refuse otherwise. |
| `persist_confirmed(confirmation_id, expected_payload_hash)` | Atomically consume a `CONFIRMED` intent once and insert the task; returns `(task_id, duplicate)`. |
| `persist_authorized(payload, authorization_record)` | Idempotently persist an enterprise capture; returns `{"task_id", "duplicate", "payload_hash"}` — or `{"pending": true}` if the backend commits asynchronously. The same `capture_session_id` must never create a second task; the same session id with different content must be refused. |
| `read_task(task_id)` | Stored record including the payload and capture metadata, or `None`. |
| `similar_tasks(task_type, limit)` | Candidate matches by normalized task type — candidates, not rankings. |
| `verify_evidence_chains()` | Mechanically recompute evidence chains; returns a status dict. |

Failures raise `StorageError` with a safe, deployment-agnostic message (or a `CaptureError` subclass for semantic refusals such as a session conflict). Raw driver exceptions must not leak internals to the caller.

## Verifying an enterprise adapter

`tests/test_adapter_contract.py` is a reusable contract suite: subclass `AdapterContractTests` with the deployment's `make_adapter()` and run it against the real adapter before production use. The suite covers confirmation state transitions, consumption-once, idempotent session persistence, session-conflict refusal, read-back, similar-task lookup, schema readiness and chain verification. The in-memory reference adapter (`tests/fixtures/memory_adapter.py`) demonstrates a complete conforming implementation.
