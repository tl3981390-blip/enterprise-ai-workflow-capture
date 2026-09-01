# Changelog

## 2.0.1 - 2026-09-01

Security boundary patch: harness-trusted inputs are now actually attested. No product redesign; all v2.0.0 product behaviors preserved.

- Root cause closed: the host model could previously self-authorize via unsigned grants, model-environment HMAC signers, self-chosen session ids and `harness_provided` strings.
- Added HARNESS_CAPTURE_ASSERTION: Ed25519-signed per-capture assertions verified against a deployment trust root; the runtime only verifies and ships no production signer.
- `capture_session_id` and harness-owned business/AI context are injected only from the verified assertion; candidates carrying them are rejected.
- Added `VerifiedHarnessCaptureContext`: the single object that may carry harness-trusted facts, constructible only by the verifier.
- Added trust classes: `PRODUCTION_ENTERPRISE` vs `DEVELOPMENT_TEST_ONLY`; unsigned/HMAC local grants are dev-only and refused under `WORKFLOW_CAPTURE_MODE=PRODUCTION_ENTERPRISE`.
- Authorization records now carry verification level and trust class, never keys or signatures.
- `scripts/make_grant.py` replaced by `scripts/make_test_grant.py`; added `scripts/make_test_assertion.py` (throwaway-key local Ed25519 minter) and `scripts/check_release_hygiene.py` (SKILL.md YAML + discovery check).
- Added TRUST-001…013 adversarial tests; suite now 94 tests (76 preserved).
- Ed25519 verification uses the mature `cryptography` package (optional `enterprise` extra); no cryptography is implemented in this repository.

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
