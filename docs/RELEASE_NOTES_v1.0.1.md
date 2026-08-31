# v1.0.1

This patch release fixes two integrity boundaries without expanding product scope.

- Human confirmation is now a database-backed `PREPARED → CONFIRMED → CONSUMED` state machine. Prepare exposes no commit token. The CLI confirmation step requires an interactive terminal, records method plus optional lawful identity/source, and Commit atomically consumes the exact confirmed payload once.
- Internal Evidence content hashes are computed only from canonical sanitized evidence. Caller-supplied `content_hash` is rejected. External digests are stored separately with algorithm, source and verification state. Doctor mechanically recomputes new Evidence chains and reports tampering.
- Schema v3 migrates v2 confirmations as consumed legacy records and marks pre-v3 Evidence `legacy_unverified` rather than retroactively trusting it.

`PENDING_EXTERNAL_VALIDATION`: target harnesses do not yet expose a standardized signed human-confirmation attestation. The repository provides the strongest portable CLI boundary available: the human runs an interactive terminal challenge; piped confirmation is refused. Harness-specific signed identity/source integration remains deployment work.
