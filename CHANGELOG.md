# Changelog

## 1.0.1 - 2026-09-01

- Made human confirmation a database-backed `PREPARED → CONFIRMED → CONSUMED` gate.
- Removed the Prepare-time confirmation token and added interactive CLI confirmation.
- Bound internal Evidence hashes to canonical sanitized content and separated external digest metadata.
- Added Evidence chain verification and a v2-to-v3 compatibility migration.

## 1.0.0 - 2026-08-31

- First stable release.
- Added explicit prepare/confirm/commit workflow with redaction and read-back verification.
- Added normalized SQLite schema, stable UUID identifiers, evidence hash chain, lineage, external-reference hashing and schema migrations.
- Added task read-back, conservative similar-task lookup, deterministic release builder and self-contained installer.
- Added 16 automated acceptance and boundary tests covering the 11 required scenarios.
