---
name: enterprise-ai-workflow-capture
description: Capture a completed human-AI work process from the current legally provided conversation, sanitize it, obtain human confirmation, persist it with lineage, and query how work was actually completed. Use when a user explicitly asks to record, capture, or deposit the current task workflow; do not use for passive monitoring, chat archiving, or AI usage counting.
license: MIT
metadata:
  version: "1.0.0"
  language: "en,zh-CN"
---

# Enterprise AI Workflow Capture

Capture **how a real task was completed**, not a transcript and not an employee score.

## Hard boundaries

- Run only after an explicit user request such as “记录这次流程” or “沉淀这次任务”.
- Use only the current conversation context legally supplied by the harness and facts the user supplies. Never inspect other conversations, applications, devices, business systems, or employee data.
- Never persist a draft without an explicit confirmation in the current interaction. Preparing a draft is reversible; committing it is a separate action.
- Sanitize before persistence. Never persist passwords, tokens, API keys, private keys, personal identifiers, payment-card data, private contact details, unauthorized source text, or unnecessary confidential content.
- Preserve uncertainty and provenance. AI inference is not observation. A human correction supersedes a draft but does not rewrite historical evidence.
- Do not calculate employee performance, rank people, or claim a `BEST_KNOWN_PATH` from insufficient evidence.

## Capture workflow

1. Reconstruct the task boundary from the current conversation: goal, start/end, actors, actions, corrections, retries, failures, recoveries, final result, adoption state, prerequisites, and business references.
2. Express the candidate using [references/capture-contract.md](references/capture-contract.md). Keep only minimal sanitized evidence excerpts or hashes; never copy the whole conversation by default.
3. Write the candidate JSON to a user-approved workspace location and run:

   ```bash
   python scripts/flow_capture.py prepare --input <candidate.json> --output <confirmation.json>
   ```

4. Show the compact confirmation summary. Call out redactions, uncertain/inferred fields, retained evidence, final adoption state, and anything intentionally excluded. Let the user edit or delete fields.
5. Only after the user explicitly confirms, run the commit with the exact token from the prepared artifact:

   ```bash
   python scripts/flow_capture.py commit --confirmation <confirmation.json> --token <token> --db <workflow.db>
   ```

6. Read back the committed record and compare its `confirmed_payload_hash` with the prepared artifact. Report the stable `task_id`, persisted status, redaction count, and database path.

If preparation reports `confirmation_required`, ask only for facts that materially affect process fidelity or privacy. Unknown is valid; never invent missing steps. If the user declines confirmation, do not commit.

## Queries

- “这个任务当时怎么完成？” → `show --task-id <id>`; present steps, corrections, failures, recovery, result and lineage.
- “最近类似任务有哪些？” → `similar --task-type <type>`; treat results as candidates based on normalized task type and path signature, not semantic truth.
- Path comparison or automation candidates → read [references/analysis-policy.md](references/analysis-policy.md). Derived knowledge must cite source task/path IDs and remain revisable.

## Operational rules

- Default database: a path explicitly chosen by the user or `<workspace>/.workflow-capture/workflows.db`. Do not silently write outside the current workspace.
- The CLI uses SQLite transactions, foreign keys, append-only event lineage, schema migrations, UUID business identifiers, and read-back verification. SQLite row IDs are never business identity.
- Use `doctor` before first use and after installation. Use `migrate` after upgrading. Back up a material database before a migration; never downgrade it in place.
- For schema details and migrations, read [references/data-model.md](references/data-model.md).
- For privacy decisions, read [references/privacy-policy.md](references/privacy-policy.md).

## Completion evidence

A capture is complete only when the user confirmed the sanitized candidate, commit returned success, read-back hash matched, and a subsequent `show` returns the same confirmed content. A model statement or draft file is not persistence evidence.

