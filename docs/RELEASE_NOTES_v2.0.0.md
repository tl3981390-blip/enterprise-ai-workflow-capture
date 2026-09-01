# v2.0.0

This major release corrects the product boundary: from "occasionally save a chat workflow after interactive confirmation" to **low-friction, authorized, structured sedimentation of how mandated AI-assisted business tasks were actually completed**. v1.0.1 remains available and untouched.

## What changed

- **Enterprise Capture Authorization.** Enterprise-managed capture runs only under a harness-provided grant (`WORKFLOW_CAPTURE_AUTHORIZATION_FILE`, optional HMAC key `WORKFLOW_CAPTURE_AUTHORIZATION_KEY`). Missing, malformed, expired, out-of-scope or unverifiable authorization fails closed (exit 4). Payloads can never authorize themselves. See `references/enterprise-authorization.md`.
- **Low-friction enterprise capture.** One `capture` command: validate → authorize → sanitize → idempotent persist → read-back verify. No terminal interaction for employees. Personal explicit capture (`prepare`/`confirm`/`commit`) is preserved unchanged.
- **Storage Adapter Contract.** SQLite is the local/reference implementation; enterprises plug in their own adapter module at deployment (`references/storage-adapter-contract.md`). A reusable contract test suite and an in-memory reference adapter prove substitutability.
- **Idempotent ingestion.** Unique `capture_session_id` plus content-hash dedupe: retries, timeouts and harness replays never duplicate a task; a session id reused with different content is refused.
- **Honest capture states.** `TASK_COMPLETED_CAPTURE_PERSISTED / _PENDING / _FAILED`; persistence is claimed only after read-back; storage failure exits 5 and never masquerades as task failure.
- **Richer truthful events.** `decision` events, per-event timing (`occurred_at`, `duration_ms`), capability identity (model/skill/tool + version), structured human interventions (error vs business preference, rework, affected step), task timing, hashed business-context reference, harness-provenance department/workflow, provenance-tagged AI context. Unknown stays unknown.
- **Privacy hardening.** JWT/AWS/GitHub-token redaction added; transcript-sized evidence and oversized summaries rejected; employee-scoring and self-authorization fields rejected mechanically.
- **Schema v4** with honest legacy migration; `derived_knowledge` gains `sample_size`; the derived layer keeps no write API. Fewest steps is never "best".

## Validation performed on Windows with Python 3.14.6 and SQLite 3.50.4

- 76/76 automated tests passed — 20 preserved v1 regression + 56 v2 (enterprise capture, authorization boundaries, adapter contract, privacy/governance guards, CLI integration);
- all 18 contract adversarial scenarios executed with evidence (`evidence/v2.0.0-adversarial.md`);
- end-to-end enterprise capture with an HMAC-signed grant: persisted, read-back verified, idempotent replay; `show`/`similar`/`doctor` verified;
- v3 → v4 migration with legacy records honestly classified;
- Release ZIP extraction, offline install and installed-copy `doctor` passed in a clean directory; fresh-environment simulation (grant via environment only) passed;
- repository and release contents scanned with the redaction engine; only synthetic test fixtures and prose false positives found — no credential is present.

## PENDING_EXTERNAL_VALIDATION

- harness-native signed identity/source assertions beyond HMAC grant verification;
- organization-specific confidential-data classification policy;
- production multi-user authorization, encryption at rest, backup and retention controls;
- enterprise storage adapters (PostgreSQL / internal API): deploy and certify against the shipped contract test suite;
- external ERP/OA/CRM identity and business-object mapping;
- months of representative data before any path-quality claim (none is made by this release).
