# Privacy policy

## Data minimization

Retain process meaning, not document bodies. Evidence may be a sanitized excerpt, a content hash, or a permitted reference. Do not retain both when one is sufficient.

Automatic detection covers common credentials, bearer tokens, private keys, Chinese national identifiers, card-like numbers, email addresses and Chinese mobile numbers. Pattern detection is a safety net, not a guarantee. Business secrets and uncommon personal data require human review.

## Confirmation gate

The preview must expose redaction categories and paths, inferred steps, adoption state, step count and retained evidence. A user may correct, remove or decline. Any edit requires a fresh `prepare`; confirmation is a separate interactive transition bound to the exact payload hash. Commit atomically consumes that confirmation and cannot reuse it.

## Access and retention

SQLite file permissions, encryption at rest, retention time and deletion authority belong to the deploying enterprise. v1 does not silently select a retention period or implement remote sync. Before production use, the organization must define access control, backup encryption, retention and lawful deletion procedures.
