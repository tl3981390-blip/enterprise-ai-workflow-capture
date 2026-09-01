# Capture contract (v2)

The agent creates this candidate from only the current harness-provided conversation and facts the user supplies. Unknown values remain unknown; do not manufacture continuity, timestamps, model names, or versions.

Required fields: `task_type`, `task_goal`, `steps`, `final_result`.

**Enterprise-managed capture (v2.0.1+):** the candidate carries *task facts only*. It must **not** contain `capture_session_id`, harness-provenance business context (`business_context.department/workflow/ref` or `provenance: harness_provided`), or harness-provenance `ai_context` — those are harness-owned and are injected by the runtime from the verified assertion. Development/test capture (legacy local grant) still requires `capture_session_id` in the candidate.

```json
{
  "capture_session_id": "development/test grant path only; forbidden in attested enterprise capture",
  "task_type": "stable business-oriented label",
  "task_goal": "what the employee intended to accomplish",
  "process_summary": "brief reconstruction, not a transcript (max 4000 chars)",
  "prerequisites": ["information required before the path can work"],
  "started_at": "ISO-8601, when truly known",
  "completed_at": "ISO-8601, when truly known",
  "business_context": {
    "provenance": "user_reported (harness_provided is injected by the runtime from the verified assertion)"
  },
  "ai_context": {
    "model": "only with a real source", "provider": "...", "skill": "...", "version": "...",
    "provenance": "user_reported | observed (harness_provided only via verified assertion)"
  },
  "steps": [
    {
      "actor": "human | ai | tool | system",
      "event_type": "action | clarification | correction | retry | failure | recovery | decision | result",
      "summary": "minimal sanitized description of what happened (max 4000 chars)",
      "provenance": "observed | user_reported | ai_inferred | system_generated",
      "confidence": 0.0,
      "occurred_at": "ISO-8601, when truly available",
      "duration_ms": 0,
      "capability": {"kind": "model | skill | tool | harness", "name": "...", "version": "..."},
      "intervention": {"reason": "error | business_preference | style | other | unknown", "rework": false, "modified_step": 2},
      "metadata": {"event_version": 2}
    }
  ],
  "final_result": {
    "summary": "minimal result description",
    "adoption_status": "adopted | partially_adopted | rejected | abandoned | unknown",
    "quality_notes": "optional human-reported assessment"
  },
  "evidence": [
    {
      "evidence_type": "conversation_excerpt | file_hash | tool_result | user_confirmation",
      "source_ref": "current-session:turn-N",
      "sanitized_excerpt": "optional minimal excerpt (max 2000 chars; never a transcript)",
      "provenance": "observed"
    },
    {
      "evidence_type": "file_hash",
      "source_ref": "approved-store:document-id",
      "external_digest": "external digest value",
      "hash_algorithm": "sha256 | sha512 | blake2b",
      "verification_state": "verified | unverified",
      "provenance": "observed | user_reported"
    }
  ],
  "external_references": [
    {"namespace": "crm:customer", "external_id": "value hashed before storage", "relation": "subject"}
  ],
  "harness_metadata": {"harness": "codex", "extension": {}}
}
```

## Event vocabulary mapping

The enterprise event list maps onto `actor` + `event_type`: `HUMAN_ACTION` = `human` + `action`, `AI_RETRY` = `ai` + `retry`, `TOOL_ACTION` = `tool` + `action`, `SYSTEM_ACTION` = `system` + `action`, `CLARIFICATION/CORRECTION/RETRY/FAILURE/RECOVERY/DECISION/RESULT` carry their own `event_type`. A human edit of AI output is a `human` + `correction` step whose `intervention.reason` distinguishes an error fix from a business-preference edit, and whose `modified_step` points at the affected step.

## Rules

- `confidence` is meaningful only for `ai_inferred` and is then required in `[0, 1]`; it never turns inference into evidence.
- `content_hash` is forbidden input: the runtime computes it from canonical sanitized internal evidence. External-only evidence must use the separate digest, algorithm, source and verification fields; an external digest is never treated as the runtime's content hash.
- `capture_session_id` identifies the capture session for idempotency; it is excluded from the content hash so identical work retried under a new session still deduplicates. In attested enterprise capture it comes only from the verified assertion.
- Fields that score or rank people (`employee_score`, `ai_usage_score`, rankings, …) are rejected mechanically. Fields that claim authorization or select trust (`capture_authorized`, `authorization`, `grant_id`, `trust_root`, `public_key`, `verifier`, `issuer`, `assertion`, `signature`, …) are rejected mechanically: authority is a verified harness fact, never payload content.
- `business_context.ref` and every `external_references.external_id` are hashed before persistence.
