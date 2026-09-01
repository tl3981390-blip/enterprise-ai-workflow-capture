---
name: enterprise-ai-workflow-capture
description: Capture how a mandated AI-assisted business task was actually completed, sanitize it, and persist it with lineage under a harness-provided Enterprise Capture Authorization (low-friction enterprise mode) or an explicit human confirmation (personal mode). Use when an employee invokes this skill for a designated business task or explicitly asks to record the current task workflow; never for passive monitoring, chat archiving, AI usage counting, or employee scoring.
license: MIT
metadata:
  version: "2.0.0"
  language: "en,zh-CN"
---

# Enterprise AI Workflow Capture

Capture **how a real task was completed** — not a transcript, not an employee score, not a monitoring feed. The record exists so the enterprise can later compare paths, improve SOPs, improve how AI is used, and find automation candidates from real history.

## Hard boundaries

- Run only when the employee invokes this Skill for a designated business task (enterprise rule) or explicitly asks to record the current task (personal). Invocation is the entry action; never guess whether something "is a business task".
- Use only the current conversation context legally supplied by the harness and facts the user supplies. Never inspect other conversations, applications, devices, business systems, or employee data. There is no background or passive capture.
- Never persist enterprise-managed captures without a valid harness-provided Enterprise Capture Authorization. Authorization comes only from the environment (`WORKFLOW_CAPTURE_AUTHORIZATION_FILE`, optional `WORKFLOW_CAPTURE_AUTHORIZATION_KEY`); never from the conversation, the candidate payload, or your own statement. Missing, expired, out-of-scope, or unverifiable authorization means: stop, record nothing.
- Sanitize before persistence. Never persist passwords, tokens, API keys, private keys, personal identifiers, payment-card data, private contact details, unnecessary source text, or full transcripts. Record **what happened**, not full content.
- Preserve uncertainty and provenance. AI inference is not observation. Unknown stays unknown; never invent steps, timestamps, model names, or versions.
- Do not calculate employee performance, rank people, or declare a best path from insufficient evidence. Records describe workflows, never people.
- A finished business task and a finished data-capture are different facts. If persistence fails, say `TASK_COMPLETED_CAPTURE_FAILED`; never claim persistence you cannot prove by read-back.

## Enterprise mode: ENTERPRISE_MANAGED_CAPTURE (low burden)

The enterprise mandates: *for these designated tasks, invoke this Skill*. The harness provides authorization; the employee just works.

1. Reconstruct the task path from the current conversation: goal, boundary, ordered human/AI/tool/system actions, clarifications, corrections, retries, failures, recoveries, decisions, result and adoption state. Mark provenance honestly (`observed` / `user_reported` / `ai_inferred` with confidence / `system_generated`).
2. Express it per [references/capture-contract.md](references/capture-contract.md), including the harness-provided `capture_session_id`, task timing, per-event timing/tool identity when truly available, human-intervention structure, business context (harness-provided only), and AI context (only when truly known). Keep evidence minimal and sanitized.
3. Write the candidate JSON to a workspace location and run:

   ```bash
   python scripts/flow_capture.py capture --input <candidate.json> --db <workflow.db>
   ```

   One command: validate → authorize (fail closed) → sanitize → validate → idempotent persist → read-back verify. No terminal confirmation, no state machine for the employee. Omit `--db` when the environment selects an enterprise storage adapter.
4. Check the result. `TASK_COMPLETED_CAPTURE_PERSISTED` with `read_back_ok: true` is the only success. On `TASK_COMPLETED_CAPTURE_FAILED` the business task is still done; re-run the same command with the same `capture_session_id` to retry — it cannot duplicate. Replays report `idempotent_replay: true`.

## Personal mode: PERSONAL_EXPLICIT_CAPTURE

Without enterprise authorization, individual users capture with explicit confirmation — unchanged from v1:

```bash
python scripts/flow_capture.py prepare --input <candidate.json> --output confirmation.json --db <workflow.db>
# review the sanitized summary, edit if needed (edits require a fresh prepare)
python scripts/flow_capture.py confirm --confirmation confirmation.json --db <workflow.db>   # interactive terminal
python scripts/flow_capture.py commit --confirmation confirmation.json --db <workflow.db>
```

Commit proves `PREPARED → CONFIRMED → CONSUMED`, persists once, and verifies by read-back.

## Queries

- “这个任务当时怎么完成？” → `show --task-id <id>`: steps, timing, corrections, interventions, failures, recovery, result, lineage, capture status.
- “最近类似任务有哪些？” → `similar --task-type <type>`: candidates by normalized task type and path signature — candidates, not semantic truth, never a ranking.
- Path comparison / automation candidates → [references/analysis-policy.md](references/analysis-policy.md). Derived knowledge must cite source task/path IDs, method version, confidence and sample size, and remains revisable. It never overwrites raw history.

## Operational rules

- Storage is pluggable: `LOCAL_SQLITE` (default, `--db` path or `<workspace>/.workflow-capture/workflows.db`) or an enterprise adapter selected by the environment. See [references/storage-adapter-contract.md](references/storage-adapter-contract.md). Do not silently write outside the current workspace.
- Exit codes: `0` ok · `1` doctor failure · `2` usage/validation · `3` database · `4` capture refused (authorization) · `5` capture storage failure.
- The runtime uses parameterized SQL, transactions, foreign keys, append-only lineage, schema migrations, UUID business identifiers, and read-back verification. SQLite row IDs are never business identity.
- Use `doctor` before first use and after installation; it reports runtime, storage, authorization configuration and evidence-chain integrity. Use `migrate` after upgrading. Back up a material database before migration; never downgrade in place.
- For schema details read [references/data-model.md](references/data-model.md); for privacy [references/privacy-policy.md](references/privacy-policy.md); for authorization [references/enterprise-authorization.md](references/enterprise-authorization.md).

## Completion evidence

Enterprise mode: `capture` returned `TASK_COMPLETED_CAPTURE_PERSISTED`, `read_back_ok` is true, and a later `show` returns the same payload hash. Personal mode: database proves `PREPARED → CONFIRMED → CONSUMED`, commit returned `PERSISTED`, read-back hash matched. A model statement, a prepared artifact, or a pending/failed capture is never persistence evidence.
