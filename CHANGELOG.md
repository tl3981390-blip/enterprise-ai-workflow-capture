# Changelog

## 2.0.0 - 2026-09-01

Product correction: from "occasionally save a chat workflow after interactive confirmation" to "low-friction, authorized sedimentation of real AI-assisted task paths" — while keeping every v1 truthfulness mechanism.

- Added Enterprise Capture Authorization: harness-provided grant via environment, fail-closed, optional HMAC-SHA256 verification, scope/expiry/storage checks; payloads can never self-authorize.
- Added enterprise one-shot `capture` command: validate → authorize → sanitize → idempotent persist → read-back; no interactive confirmation for mandated tasks.
- Kept personal explicit capture (`prepare`/`confirm`/`commit`) unchanged and fully regressed.
- Added Storage Adapter Contract: `LOCAL_SQLITE` reference implementation plus environment-selected enterprise adapters; reusable contract test suite and in-memory reference adapter.
- Added capture identity and idempotency: unique `capture_session_id`, content-hash dedupe, session-conflict refusal.
- Added honest capture states `TASK_COMPLETED_CAPTURE_PERSISTED / _PENDING / _FAILED` with dedicated exit codes 4 (authorization refusal) and 5 (storage failure).
- Extended the event model: `decision` events, per-event `occurred_at`/`duration_ms`/`capability`/`intervention`, task timing, business context (hashed ref, harness-provenance department/workflow), AI context with provenance.
- Hardened privacy: JWT/AWS/GitHub-token redaction, transcript-sized evidence and oversized summaries rejected, employee-scoring and self-authorization fields rejected mechanically.
- Schema v4 migration with honest legacy classification; `derived_knowledge` gains `sample_size`; derived layer keeps no write API.
- 76 automated tests (20 preserved v1 regression + 56 v2), including the 18-scenario adversarial matrix.

## 1.0.1 - 2026-09-01

- Made human confirmation a database-backed `PREPARED → CONFIRMED → CONSUMED` gate.
- Removed the Prepare-time confirmation token and added interactive CLI confirmation.
- Bound internal Evidence hashes to canonical sanitized content and separated external digest metadata.
- Added Evidence chain verification and a v2-to-v3 compatibility migration.

## 1.0.0 - 2026-08-31

- First stable release.
- Added explicit prepare/confirm/commit workflow with redaction and read-back verification.
- Added normalized SQLite schema, stable UUID identifiers, evidence hash chain, lineage, external-reference hashing and schema migrations.
- Added task read-back, conservative similar-task lookup, deterministic release builder and self-contained installer.
- Added 16 automated acceptance and boundary tests covering the 11 required scenarios.
