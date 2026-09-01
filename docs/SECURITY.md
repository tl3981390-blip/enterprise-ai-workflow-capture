# Security model

The Skill is active-call only. It has no background service, network client, screen capture, keyboard/mouse listener, cross-session reader, ERP/CRM/OA connector, or production-data copier. The package contains no network, subprocess, threading or ctypes facilities — a mechanical test asserts this. The runtime contains **no signer**: `Ed25519PrivateKey` appears only in the local test-only minter and tests, never in the runtime package (mechanically asserted).

## Trust boundary (v2.0.1)

**Model data is not harness-trusted data.** The host model submits task facts; it can never create enterprise authority or harness-owned context.

- Enterprise capture requires an Ed25519-signed harness assertion (`WORKFLOW_CAPTURE_ASSERTION`) verified against the deployment-protected trust root (`WORKFLOW_CAPTURE_TRUST_ROOT`); `WORKFLOW_CAPTURE_MODE` can enforce `PRODUCTION_ENTERPRISE` / `DEVELOPMENT_TEST` class matching.
- The trust root, verifier, issuer and keys can never be selected by the candidate or by CLI flags; payload fields attempting so are rejected.
- `capture_session_id` and harness-owned business/AI context are injected only from the verified assertion; a candidate carrying them is rejected; a `harness_provenance` string is never accepted as proof.
- The assertion binds session, task scope, storage scope, business context, issuer, identity, nonce and validity window; tampering with any signed field fails closed.
- Unsigned grants and HMAC local grants are DEVELOPMENT_TEST_ONLY and refused under `PRODUCTION_ENTERPRISE`; they can never produce production-trusted persistence.
- The persisted authorization record contains the verification level and trust class — never keys, signatures, or secrets.

Remaining deployment-side responsibility (harness): protecting the trust root and the private key, and invoking the runtime with a protected environment. A model with arbitrary control over its own process environment cannot be distinguished from the harness by any in-process mechanism; the mechanical boundary here ensures no valid production assertion can be *produced* without the harness private key.

## Other security-critical invariants

- sanitize before validation and persistence; re-sanitize immediately before commit;
- personal mode keeps the database-backed `PREPARED → CONFIRMED → CONSUMED` state machine with interactive confirmation and exact payload-hash binding;
- system-computed internal Evidence digests, typed external digest claims and mechanical chain verification;
- persistence is idempotent per verified session and per content hash; a session id reused with different content is refused;
- capture status is honest: `TASK_COMPLETED_CAPTURE_PERSISTED / _PENDING / _FAILED`; persistence is claimed only after read-back verification;
- SQLite transactions, parameterized queries, foreign keys and read-back verification;
- minimal evidence (size-capped), hashed business/external identifiers, no secret logging;
- records describe workflows, never people: scoring/ranking fields are rejected mechanically;
- derived claims stay separated from observations, carry sample size and method version, and are traceable by lineage; this runtime ships no derived-write API.

Exit codes distinguish refusal from failure: `4` = capture refused (authorization), `5` = capture storage failure, `2` = usage/validation, `3` = database, `1` = doctor integrity failure.

Known boundary: regex detection cannot recognize every possible enterprise secret or contextual confidential fact. Deployment therefore requires organization-specific policy and review. Database encryption, multi-user authorization, assertion issuance and key custody, trust-root protection, retention, and harness-protected process environments are infrastructure responsibilities outside this local runtime (see `docs/RELEASE_NOTES_v2.0.1.md`).
