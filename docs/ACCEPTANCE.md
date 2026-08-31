# Acceptance matrix

The automated suite covers: one-shot success; multi-turn clarification; human correction after AI failure; abandoned failure; partial adoption; secret redaction; similar-task lookup; corrected draft requiring re-prepare; different paths for one task type; preservation of analysis/lineage inputs; and migration from schema v1 to v2.

It also covers invalid input, unconfirmed commit refusal, one-time confirmation consumption, modified-payload re-confirmation, forged internal hashes, typed external digests, Evidence tamper detection, persistence after reconnect, migration, database integrity and installer self-check. Production harness-native signed identity assertions, organization-specific confidential-data classification, multi-user database authorization and external enterprise-system identity mapping require deployment-specific validation.
