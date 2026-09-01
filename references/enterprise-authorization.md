# Enterprise Capture Authorization

Enterprise-managed capture runs only under a harness-provided authorization grant. The Skill never decides on its own that it may capture; the enterprise/harness supplies the authorization fact through the environment, and the runtime fails closed whenever that fact is missing, malformed, expired, out of scope, or unverifiable.

## Provided by the harness / enterprise deployment

| Environment variable | Meaning |
|---|---|
| `WORKFLOW_CAPTURE_AUTHORIZATION_FILE` | Path to the grant JSON issued by the enterprise/harness. |
| `WORKFLOW_CAPTURE_AUTHORIZATION_KEY` | Optional HMAC-SHA256 verification key. When set, every grant must carry a valid `signature`. Kept only in the environment or a key service — never in this repository, a payload, or a CLI flag. |

The grant:

```json
{
  "grant_version": 1,
  "grant_id": "grant_…",
  "issuer": "harness/enterprise identifier",
  "mode": "ENTERPRISE_MANAGED_CAPTURE",
  "capture_authorized": true,
  "capture_scope": {"task_types": ["supplier-quote-comparison"], "departments": ["procurement"]},
  "storage_scope": {"adapter": "local_sqlite"},
  "retention_policy": "enterprise policy reference",
  "issued_at": "ISO-8601",
  "expires_at": "ISO-8601",
  "signature": "hex HMAC-SHA256 over the grant without this field (optional)"
}
```

`"*"` (or a list containing `"*"`) in a scope list means unrestricted within that dimension. `task_types` and `departments` are matched on normalized labels.

## Mechanical rules

1. The grant path and the key come only from the environment. A candidate payload, CLI flag, or conversation message carrying anything like `capture_authorized` / `authorization` / `grant_id` is rejected as a self-authorization attempt.
2. Missing file, unreadable file, missing required fields, `capture_authorized` not exactly `true`, unknown `mode`, malformed timestamps, or an expired grant → refuse, persist nothing (exit code 4).
3. Signature discipline: key configured + unsigned grant → refuse; key configured + bad signature → refuse; signature present + no key configured → refuse (unverifiable grants are not silently trusted). Only key configured + valid signature reports `hmac_sha256_verified`; an unsigned grant without a configured key is recorded honestly as `harness_asserted_unverified`.
4. Scope checks per capture: `task_type` inside `capture_scope.task_types`; the configured storage adapter kind inside `storage_scope.adapter`; harness-provided `department` inside `capture_scope.departments` (when restricted).
5. Enterprise mode requires the grant `mode` = `ENTERPRISE_MANAGED_CAPTURE` and a harness-provided `capture_session_id`. Personal explicit capture does not consult the grant.
6. Every persisted enterprise record carries a public authorization record (grant id, issuer, mode, retention policy reference, verification level, check time) — never the key or the signature.

## Deployment note

`scripts/make_grant.py` issues a signed grant for local testing using the key from the environment. In production, grant issuance, key distribution, identity, SSO, retention and deletion are harness/enterprise responsibilities — outside this Skill.
