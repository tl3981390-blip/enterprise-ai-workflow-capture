# Acceptance matrix

The automated suite (76 tests) covers:

**Personal-mode regression (v1, preserved):** one-shot success; multi-turn clarification; human correction after AI failure; abandoned failure; partial adoption; secret redaction; similar-task lookup; corrected draft requiring re-prepare; different paths for one task type; analysis/lineage inputs; schema migration with old-record read-back; invalid input; unconfirmed commit refusal; one-time confirmation consumption; forged internal hashes; typed external digests; evidence tamper detection; persistence after reconnect; newer-database refusal; interactive-terminal confirmation boundary.

**v2 enterprise capture:** one-shot authorized capture with read-back; v2 event fields (decision, timing, capability, intervention, business context, AI context); idempotent replay per session; content dedupe across sessions; session-conflict refusal; HMAC-verified grants; honest `TASK_COMPLETED_CAPTURE_FAILED` on storage timeout with clean single-record retry; honest `_PENDING`; read-back mismatch never claims persistence; adapter internals never leak into errors; unknown AI context stays unknown.

**Authorization boundary:** no grant / unauthorized / expired / out-of-scope task type / storage-scope mismatch / personal-mode grant / missing session id / forged signature / signed-without-key / unsigned-with-key / unreadable / malformed — all fail closed; payload-carried authorization claims rejected at validation; department scope and provenance enforced.

**Privacy and governance:** employee-scoring fields rejected (root and nested); transcript-sized evidence and oversized summaries rejected; `ai_inferred` requires confidence; invalid timing rejected; JWT/AWS/GitHub-shaped secrets redacted; no network/background facilities in the package (static scan); no derived-write or raw-overwrite API; similar() carries no best/score/rank fields; cross-task isolation.

**Storage adapter contract:** the shared contract suite passes against LOCAL_SQLITE and the in-memory reference adapter (confirmation round-trip, consumption-once, idempotent sessions, conflict refusal, read-back, similar, chains, schema).

**CLI integration:** exit 4 without authorization, exit 5 on storage failure with recovery on retry, exit 0 idempotent replay, doctor authorization surface.

`PENDING_EXTERNAL_VALIDATION`: harness-native signed identity/source assertions beyond HMAC grants; organization-specific confidential-data classification; production multi-user authorization, encryption, backup and retention; enterprise adapter implementations (PostgreSQL/internal API) run against the contract suite at deployment; external ERP/OA/CRM identity mapping.
