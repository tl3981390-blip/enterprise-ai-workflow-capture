# Enterprise Capture Authorization

Enterprise-managed capture runs only under a **verified harness assertion**. The Skill never decides on its own that it may capture, and the host model can never create enterprise authority: it cannot mint assertions, select the trust root, choose the verifier, or claim harness provenance as a string.

## Trust model

```text
Harness / Enterprise deployment (holds the Ed25519 private key, outside this Skill)
  → signs a per-capture HARNESS_CAPTURE_ASSERTION
  → runtime verifies it against the deployment-protected trust root
  → only then does a VerifiedHarnessCaptureContext exist
  → capture_session_id and harness-owned context are injected from it
```

The runtime contains **no signer**. `scripts/make_test_grant.py` and `scripts/make_test_assertion.py` are LOCAL TESTING ONLY: their outputs carry `trust_class = DEVELOPMENT_TEST_ONLY` and are refused whenever `WORKFLOW_CAPTURE_MODE=PRODUCTION_ENTERPRISE`.

## Environment interface (provided by the harness / deployment)

| Environment variable | Meaning |
|---|---|
| `WORKFLOW_CAPTURE_ASSERTION` | Path to the per-capture signed assertion JSON. |
| `WORKFLOW_CAPTURE_TRUST_ROOT` | Path to the deployment-protected trust root JSON pinning trusted issuers to Ed25519 public keys. |
| `WORKFLOW_CAPTURE_MODE` | Optional explicit enforcement: `PRODUCTION_ENTERPRISE` or `DEVELOPMENT_TEST`. A class mismatch fails closed. |
| `WORKFLOW_CAPTURE_AUTHORIZATION_FILE` / `WORKFLOW_CAPTURE_AUTHORIZATION_KEY` | Legacy local grant channel — DEVELOPMENT_TEST_ONLY, refused under `PRODUCTION_ENTERPRISE`. |

The assertion:

```json
{
  "assertion_version": 1,
  "assertion_id": "unique assertion identity",
  "issuer": "trusted issuer name pinned in the trust root",
  "key_id": "optional pinned key identifier",
  "capture_authorized": true,
  "mode": "ENTERPRISE_MANAGED_CAPTURE",
  "capture_session_id": "harness-owned idempotency identity",
  "capture_scope": {"task_types": ["supplier-quote-comparison"], "departments": ["procurement"]},
  "business_context": {"department": "procurement", "workflow": "sourcing", "business_context_ref": "po-…"},
  "storage_scope": {"adapter": "local_sqlite"},
  "retention_policy": "enterprise policy reference",
  "issued_at": "ISO-8601",
  "expires_at": "ISO-8601",
  "nonce": "unique per assertion",
  "signature": "base64 Ed25519 over this object without the signature field"
}
```

The trust root:

```json
{
  "trust_root_version": 1,
  "trust_class": "PRODUCTION_ENTERPRISE",
  "trusted_issuers": {
    "enterprise-harness": {"algorithm": "Ed25519", "key_id": "ent-key-1", "public_key": "base64"}
  }
}
```

## Mechanical rules

1. The trust root and assertion come only from the environment; candidates and CLI flags cannot select them. Payload fields such as `trust_root`, `public_key`, `verifier`, `issuer`, `assertion`, `signature`, `capture_authorized` are rejected mechanically.
2. Missing configuration, untrusted issuer, key mismatch, bad signature, expired or malformed assertion, missing session binding → refuse, persist nothing (exit code 4).
3. The assertion binds session, task scope, storage scope, business context, issuer, validity window and identity. Tampering with any signed field fails verification. The candidate's `task_type` and the configured storage adapter must be inside the verified scopes.
4. `capture_session_id` exists only inside the verified context. A candidate carrying it is rejected. The same holds for `business_context.department/workflow/ref` and any `harness_provided` provenance claim — the runtime injects them from the verified assertion.
5. The persisted authorization record stores `assertion_id`, `issuer`, `verification: asymmetric_signature_verified`, `trust_class`, `retention_policy`, `verified_at` — never keys, signatures, or verifier internals.
6. `DEVELOPMENT_TEST_ONLY` results are local test data. They must never be presented as production enterprise security evidence.

## Development and production

- **Production**: harness signs per-capture assertions; the trust root is deployment-protected configuration. Requires the `cryptography` package (Ed25519).
- **Development**: `scripts/make_test_assertion.py` mints a throwaway-key test assertion + dev trust root for local exercise of the full asymmetric path; `scripts/make_test_grant.py` mints legacy HMAC test grants. Both are marked and refused in production mode.

Grant/assertion issuance, private-key custody, trust-root protection, identity, SSO, retention and deletion are harness/enterprise responsibilities — outside this Skill.
