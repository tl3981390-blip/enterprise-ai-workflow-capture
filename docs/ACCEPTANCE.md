# Acceptance matrix

The automated suite covers: one-shot success; multi-turn clarification; human correction after AI failure; abandoned failure; partial adoption; secret redaction; similar-task lookup; corrected draft requiring re-prepare; different paths for one task type; preservation of analysis/lineage inputs; and migration from schema v1 to v2.

It also covers invalid input, wrong confirmation token, duplicate commit idempotency, persistence after reconnect, unknown task, limits, database integrity and installer self-check. Production harness behavior, organization-specific confidential-data classification, multi-user database authorization and external enterprise-system identity mapping require deployment-specific validation.

