# Install, update and rollback

Use a versioned GitHub Release asset, not a moving branch archive. Verify the asset against the release `SHA256SUMS.txt`, extract it, then run `scripts/install.py --target <skills-dir>`. The installer is offline and executes `doctor` on the installed copy.

## Enterprise configuration (harness/deployment)

- `WORKFLOW_CAPTURE_ASSERTION` — path to the per-capture Ed25519-signed harness assertion (see `references/enterprise-authorization.md`).
- `WORKFLOW_CAPTURE_TRUST_ROOT` — path to the deployment-protected trust root (trusted issuers → public keys). The model can never select it.
- `WORKFLOW_CAPTURE_MODE` — optional `PRODUCTION_ENTERPRISE` / `DEVELOPMENT_TEST` enforcement.
- `WORKFLOW_CAPTURE_AUTHORIZATION_FILE` / `WORKFLOW_CAPTURE_AUTHORIZATION_KEY` — legacy local grant channel; DEVELOPMENT_TEST_ONLY.
- `WORKFLOW_CAPTURE_STORAGE` — `local_sqlite` (default) or `enterprise_adapter`.
- `WORKFLOW_CAPTURE_STORAGE_ADAPTER_MODULE` — enterprise-supplied adapter module implementing `references/storage-adapter-contract.md`.
- `WORKFLOW_CAPTURE_DB` — default local database path when `--db` is omitted.

Attested verification requires the `cryptography` package (`pip install cryptography` or the `enterprise` extra). Credentials and private keys live only with the harness/enterprise deployment or a key service — never in this repository, candidate payloads, or CLI flags. The Skill ships no production signer.

## Update

Back up the database and record the current Release tag and asset digest. Install the new Skill into a staging directory, run `doctor --db <copy-of-db>`, migrate the copy, and run the acceptance suite. Only then replace the installed Skill and migrate the real database.

## Rollback

Code rollback means reinstalling the prior immutable Release asset (v1.0.1 remains available and untouched). Data rollback means restoring the pre-migration backup. Never point an older binary at a database whose schema is newer than it supports.
