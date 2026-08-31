# Security model

The Skill is active-call only. It has no background service, network client, screen capture, keyboard/mouse listener, cross-session reader, ERP/CRM/OA connector, or production-data copier.

Security-critical invariants:

- sanitize before validation and persistence;
- exact payload hash plus confirmation token before commit;
- re-sanitize immediately before commit;
- SQLite transaction, foreign keys and read-back verification;
- minimal evidence, hashed external identifiers, no secret logging;
- derived claims are separated from observations and traceable by lineage.

Known boundary: regex detection cannot recognize every possible enterprise secret or contextual confidential fact. Deployment therefore requires human review and organization-specific policy. Database encryption and multi-user authorization are infrastructure responsibilities outside this local v1 runtime.

