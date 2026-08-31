# Capture contract

The agent creates this candidate from only the current harness-provided conversation. Unknown values remain unknown; do not manufacture continuity.

Required fields:

```json
{
  "task_type": "stable business-oriented label",
  "task_goal": "what the employee intended to accomplish",
  "process_summary": "brief reconstruction, not a transcript",
  "prerequisites": ["information required before the path can work"],
  "steps": [
    {
      "actor": "human | ai | tool | system",
      "event_type": "action | clarification | correction | retry | failure | recovery | result",
      "summary": "minimal sanitized description of what happened",
      "provenance": "observed | user_reported | ai_inferred | system_generated",
      "confidence": 0.0,
      "metadata": {"event_version": 1}
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
      "sanitized_excerpt": "optional minimal excerpt",
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

`confidence` is meaningful only for `ai_inferred`; it does not turn inference into evidence. `content_hash` is forbidden input: the runtime computes it from canonical sanitized internal evidence. External-only evidence must use the separate digest, algorithm, source and verification fields; an external digest is never treated as the runtime's content hash.
