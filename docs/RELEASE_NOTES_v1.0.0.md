# v1.0.0

This is the first stable release of `enterprise-ai-workflow-capture`.

The release captures confirmed human-AI process data from an explicitly invoked current conversation. It separates sanitized observation evidence, structured process records and revisable derived knowledge. It does not monitor employees, archive full chats, score AI use, connect to enterprise systems, or automatically declare a best path.

Validation performed on Windows with Python 3.14 and SQLite 3.50.4:

- 16/16 automated acceptance and negative tests passed;
- end-to-end CLI prepare/commit/read-back/similar/doctor passed;
- SQLite foreign-key and integrity checks passed;
- migration v1 → v2 with old-record read-back passed;
- Release ZIP extraction, offline install and installed-copy self-check passed;
- Skill structural validator passed in UTF-8 mode;
- repository and Release contents scanned for credential-shaped material; only synthetic detector fixtures were used and no credential is present.

`PENDING_EXTERNAL_VALIDATION`:

- real employee invocation through each target harness beyond the repository-local CLI;
- organization-specific confidential-data classification policy;
- production multi-user authorization, database encryption, backup and retention controls;
- external ERP/OA/CRM identity and business-object mapping;
- months of representative data needed before any Best Known Path assessment.

