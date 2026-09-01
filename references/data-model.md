# Data model and evolution

Three layers remain separate:

1. `evidence`: minimal sanitized observations, system-computed canonical content digests, typed external digest claims, append-only ordinals and a per-task SHA-256 hash chain.
2. `tasks/processes/paths/steps`: persisted structured process assets.
3. `derived_knowledge`: revisable claims such as patterns or candidate paths; every claim must be linked through `lineage` to source records. v2 exposes **no write API** for this layer; it is populated only by future, separately authorized analysis.

Business identity uses prefixed UUIDs (`task_…`, `process_…`, `step_…`, `event_…`, `path_…`). SQLite internal row positions are never exposed as identity.

`schema_migrations` records version and migration checksum. Each task stores the schema version used at commit. Forward migration is transactional; opening a newer unsupported database fails. Downgrades are restored from backup rather than attempted in place.

## Schema v4 (v2.0.0)

`tasks` additionally carries:

- `capture_session_id` — harness-provided idempotency identity (unique when present; legacy rows keep NULL rather than a fabricated identity);
- `capture_mode` — `ENTERPRISE_MANAGED_CAPTURE` or `PERSONAL_EXPLICIT_CAPTURE`;
- `capture_status` — `TASK_COMPLETED_CAPTURE_PERSISTED` on committed rows; `…_PENDING` / `…_FAILED` are reported to the caller and never faked as persisted;
- `started_at` / `completed_at` — task timing when truly known;
- `business_context_ref_hash` + `business_context_json` — business reference hashed, department/workflow only when harness-provided;
- `ai_context_json` — model/provider/skill/version with provenance, only when truly known;
- `authorization_json` — public authorization record: assertion/grant id, issuer, verification level (`asymmetric_signature_verified` or `development_test_only`), trust class (`PRODUCTION_ENTERPRISE` / `DEVELOPMENT_TEST_ONLY`), retention policy reference; never keys, signatures, or secrets.

`steps` additionally carries `occurred_at`, `duration_ms`, `capability_json` (model/skill/tool identity) and `intervention_json` (human edit reason, rework flag, affected step). `derived_knowledge` gains `sample_size`.

Legacy pre-v4 rows migrate with `capture_mode = PERSONAL_EXPLICIT_CAPTURE` and `capture_status = TASK_COMPLETED_CAPTURE_PERSISTED` — factually correct, since every pre-v4 record was explicitly confirmed and persisted. Pre-v3 evidence remains honestly `legacy_unverified`.

## What the model supports answering later

The model keeps enough honest structure for the seven enterprise questions — without computing them in v2:

1. *How are similar tasks usually completed?* — `similar_tasks` by normalized `task_type`; ordered `steps` + `path_signature` per task.
2. *Which steps fail often?* — `steps.event_type = failure` with actor, capability and position.
3. *How are failures recovered?* — `correction` / `retry` / `recovery` events ordered after each failure.
4. *Where is AI output most often edited by humans?* — `human` + `correction` steps with `intervention.reason` / `modified_step` / `rework`.
5. *Which steps take the most time?* — `duration_ms` / `occurred_at` when truly available; task `started_at` / `completed_at`.
6. *Which paths were adopted?* — `adoption_status` on tasks and paths, plus `final_result`.
7. *Which steps have automation potential?* — repeated `tool` / `ai` action patterns with capability identity across many captured paths.

Any future answer must come from the Derived layer with source task/path IDs, method version, confidence and sample size — never by rewriting raw records.

## Harness and business data

Harness-specific data belongs in `harness_metadata`; business systems use `external_references`, whose external identifier is hashed before persistence. Core actor and event types remain harness-neutral.
