# Security model

The Skill is active-call only. It has no background service, network client, screen capture, keyboard/mouse listener, cross-session reader, ERP/CRM/OA connector, or production-data copier. The package contains no network, subprocess, threading or ctypes facilities — a mechanical test asserts this.

Security-critical invariants:

- sanitize before validation and persistence; re-sanitize immediately before commit;
- enterprise capture requires a harness-provided authorization grant from the environment, fails closed without it, and verifies HMAC-SHA256 signatures when a key is configured; payloads can never authorize themselves (self-authorization fields are rejected);
- enterprise mode requires a harness-provided `capture_session_id`; persistence is idempotent per session and per content hash; a session id reused with different content is refused;
- personal mode keeps the database-backed `PREPARED → CONFIRMED → CONSUMED` state machine with interactive confirmation and exact payload-hash binding;
- system-computed internal Evidence digests, typed external digest claims and mechanical chain verification;
- capture status is honest: `TASK_COMPLETED_CAPTURE_PERSISTED / _PENDING / _FAILED`; persistence is claimed only after read-back verification; a capture failure is never presented as a task failure, nor vice versa;
- SQLite transactions, parameterized queries, foreign keys and read-back verification;
- minimal evidence (size-capped), hashed business/external identifiers, no secret logging;
- records describe workflows, never people: scoring/ranking fields are rejected mechanically;
- derived claims stay separated from observations, carry sample size and method version, and are traceable by lineage; this runtime ships no derived-write API.

Exit codes distinguish refusal from failure: `4` = capture refused (authorization), `5` = capture storage failure, `2` = usage/validation, `3` = database, `1` = doctor integrity failure.

Known boundary: regex detection cannot recognize every possible enterprise secret or contextual confidential fact. Deployment therefore requires organization-specific policy and review. Database encryption, multi-user authorization, grant issuance and key distribution, retention, and harness-native signed identity assertions are infrastructure responsibilities outside this local runtime (see `docs/RELEASE_NOTES_v2.0.0.md` for external-validation items).
