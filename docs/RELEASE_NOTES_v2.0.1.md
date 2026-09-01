# v2.0.1

Security boundary patch over v2.0.0 — no product redesign. Root cause closed: **harness-trusted inputs were not actually attested**. The host model could self-authorize enterprise capture via unsigned grants, model-environment HMAC signers, self-chosen `capture_session_id`, and `harness_provided` provenance strings.

## The fix

- **HARNESS_CAPTURE_ASSERTION**: per-capture Ed25519 assertion signed by the harness/enterprise deployment and verified by this runtime against a deployment trust root. The Skill ships no production signer; `scripts/make_test_grant.py` / `scripts/make_test_assertion.py` are LOCAL TESTING ONLY (`DEVELOPMENT_TEST_ONLY`) and are refused under `PRODUCTION_ENTERPRISE`.
- **VerifiedHarnessCaptureContext**: harness-trusted facts exist only after signature + issuer + expiry + scope verification. `capture_session_id`, department/workflow/business reference and harness-provenance AI context are injected from the verified assertion; candidates carrying them are rejected.
- **Trust-root self-selection is impossible from the payload or CLI**: `trust_root`, `public_key`, `verifier`, `issuer`, `assertion`, `signature` and authorization-claim fields are rejected mechanically; verification keys come only from the deployment trust root.
- **Authorization records** carry `verification: asymmetric_signature_verified` + `trust_class`, never keys or signatures.
- **Release hygiene**: `scripts/check_release_hygiene.py` strictly parses SKILL.md frontmatter and verifies unique harness discovery.

## Validation performed on Windows with Python 3.14.6, cryptography 50.0.1, SQLite 3.50.4

- 94/94 automated tests passed — the 76 v2.0.0 tests preserved without regression, plus 18 trust-boundary tests (TRUST-001…013 with sub-cases and mode-mismatch tests);
- upgraded adversarial matrix executed (`evidence/v2.0.1-adversarial.md`), including the strengthened attack #2: no path from candidate, environment override, self-built grant/key/assertion, or forged `harness_provided` string to enterprise authority;
- real signed-assertion E2E: persisted with `asymmetric_signature_verified`, session/context injected, idempotent replay;
- release ZIP → clean-directory install → installed-copy doctor → full suite → trust attacks → discovery hygiene: all passed;
- repository and asset mechanically scanned: no production signer, no private keys, no credential-shaped material beyond synthetic fixtures.

## PENDING_EXTERNAL_VALIDATION

- harness-protected process environment and trust-root/private-key custody (deployment responsibility — the mechanical guarantee here is that no valid production assertion can be produced without the harness private key);
- organization-specific confidential-data classification policy;
- production multi-user authorization, encryption at rest, backup and retention controls;
- enterprise storage adapters certified against the shipped contract suite at deployment;
- external ERP/OA/CRM identity and business-object mapping.

v2.0.0 remains published and untouched; this release is a security patch, not a new product.
