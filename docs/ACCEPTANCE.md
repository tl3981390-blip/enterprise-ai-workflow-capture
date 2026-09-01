# Acceptance matrix

The automated suite (94 tests) covers:

**Trust boundary (v2.0.1):** TRUST-001 forged unsigned assertion → refuse; TRUST-002 model env path to own assertion → refuse; TRUST-003 model keypair / trust-root self-selection (payload fields rejected, model-signed assertion refused, no CLI trust-root flag) → refuse; TRUST-004 legacy HMAC signer under `PRODUCTION_ENTERPRISE` → refuse (dev-only otherwise, marked); TRUST-005/006 forged or mismatched candidate session id → refuse; TRUST-007 fake `harness_provided` department → refuse; TRUST-008 context mismatch → refuse; TRUST-009 scope mismatch → refuse; TRUST-010 expired assertion → refuse; TRUST-011 tampered assertion (scope/department/session/storage/retention) → refuse; TRUST-012 real trusted assertion → PERSISTED with injected session/context, `asymmetric_signature_verified`, idempotent replay; TRUST-013 asset contains no production signer or private key (mechanical scan) and the test minter refuses production trust class. Plus trust-class mode mismatch refusal and verifier-only context construction.

**Personal-mode regression (v1, preserved):** one-shot success; multi-turn clarification; human correction after AI failure; abandoned failure; partial adoption; secret redaction; similar-task lookup; corrected draft requiring re-prepare; different paths for one task type; analysis/lineage inputs; schema migration with old-record read-back; invalid input; unconfirmed commit refusal; one-time confirmation consumption; forged internal hashes; typed external digests; evidence tamper detection; persistence after reconnect; newer-database refusal; interactive-terminal confirmation boundary.

**v2 enterprise capture:** one-shot capture with read-back; v2 event fields (decision, timing, capability, intervention, business context, AI context); idempotent replay per session; content dedupe across sessions; session-conflict refusal; dev grants marked `DEVELOPMENT_TEST_ONLY`; honest `TASK_COMPLETED_CAPTURE_FAILED` on storage timeout with clean single-record retry; honest `_PENDING`; read-back mismatch never claims persistence; adapter internals never leak into errors; unknown AI context stays unknown.

**Authorization boundary:** no grant / unauthorized / expired / out-of-scope task type / storage-scope mismatch / personal-mode grant / missing session id / forged signature / signed-without-key / unsigned-with-key / unreadable / malformed — all fail closed; payload-carried authorization claims rejected at validation; department scope and provenance enforced.

**Privacy and governance:** employee-scoring fields rejected (root and nested); transcript-sized evidence and oversized summaries rejected; `ai_inferred` requires confidence; invalid timing rejected; JWT/AWS/GitHub-shaped secrets redacted; no network/background facilities in the package (static scan); no derived-write or raw-overwrite API; similar() carries no best/score/rank fields; cross-task isolation.

**Storage adapter contract:** the shared contract suite passes against LOCAL_SQLITE and the in-memory reference adapter (confirmation round-trip, consumption-once, idempotent sessions, conflict refusal, read-back, similar, chains, schema).

**CLI integration:** exit 4 without authorization, exit 5 on storage failure with recovery on retry, exit 0 idempotent replay, doctor authorization/trust surface.

**Release hygiene:** `scripts/check_release_hygiene.py` strictly YAML-parses SKILL.md frontmatter (name, version, body placement) and verifies exactly one installed skill is discoverable by name.

`PENDING_EXTERNAL_VALIDATION`: harness-protected process environment and trust-root/private-key custody (deployment responsibility); organization-specific confidential-data classification; production multi-user authorization, encryption, backup and retention; enterprise adapter implementations certified against the contract suite at deployment; external ERP/OA/CRM identity mapping.
