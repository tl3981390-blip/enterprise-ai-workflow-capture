# Data model and evolution

Three layers remain separate:

1. `evidence`: minimal sanitized observations, append-only ordinals and a per-task SHA-256 hash chain.
2. `tasks/processes/paths/steps`: confirmed structured process assets.
3. `derived_knowledge`: revisable claims such as patterns or candidate paths; every claim must be linked through `lineage` to source records.

Business identity uses prefixed UUIDs (`task_…`, `process_…`, `step_…`, `event_…`, `path_…`). SQLite internal row positions are never exposed as identity.

`schema_migrations` records version and migration checksum. Each task stores the schema version used at commit. Forward migration is transactional; opening a newer unsupported database fails. Downgrades are restored from backup rather than attempted in place.

Harness-specific data belongs in `harness_metadata`; business systems use `external_references`, whose external identifier is hashed before persistence. Core actor and event types remain harness-neutral.

