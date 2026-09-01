# enterprise-ai-workflow-capture

A privacy-first enterprise Skill and deterministic local runtime that captures **how AI-assisted business tasks were actually completed** — as structured, sanitized, verifiable data.

It exists for the transition period before AI is deeply wired into business systems. The enterprise mandates: *when employees run these designated AI-assisted tasks, they invoke this Skill.* Employees keep working normally; the Skill turns "how this task was actually completed" into durable structured records — the raw material for later path comparison, SOP improvement, AI-usage improvement, automation-candidate discovery, and enterprise AI governance.

It is not a platform: no employee management, admin console, SSO, performance scoring, leaderboards, chat surveillance, data lake, or process-mining engine. And it is not passive monitoring: capture happens only because the employee invoked the Skill for a designated task.

## Two lawful capture modes

**ENTERPRISE_MANAGED_CAPTURE** — the harness provides an Enterprise Capture Authorization (grant file via `WORKFLOW_CAPTURE_AUTHORIZATION_FILE`, optional HMAC key via `WORKFLOW_CAPTURE_AUTHORIZATION_KEY`). One low-friction command does validate → authorize → sanitize → persist → read-back. No grant, no capture: the runtime fails closed. Authorization never comes from the conversation or the payload.

**PERSONAL_EXPLICIT_CAPTURE** — individuals keep the v1 explicit flow: prepare, review the sanitized preview, confirm interactively, commit. The confirmation is a database-backed `PREPARED → CONFIRMED → CONSUMED` one-time transition bound to the exact payload hash.

## What is recorded

- task identity: UUID `task_id`, `capture_session_id`, type, goal, timing, hashed business-context reference, harness-provided department/workflow context;
- ordered execution path: human / AI / tool / system actions, clarification, correction, retry, failure, recovery, decision, result — each with provenance, optional timing and tool/model/skill identity;
- human interventions on AI output (which step, error vs business preference, rework);
- result adoption state (`adopted | partially_adopted | rejected | abandoned | unknown`);
- minimal sanitized evidence with a tamper-evident per-task hash chain; lineage into process records.

Fewest steps is never "best". Records describe workflows, never people; scoring/ranking fields are rejected mechanically. Derived knowledge stays separate from raw records and must cite sources, method, confidence and sample size.

## Failure honesty

A completed business task and a completed capture are different facts: `TASK_COMPLETED_CAPTURE_PERSISTED` / `TASK_COMPLETED_CAPTURE_PENDING` / `TASK_COMPLETED_CAPTURE_FAILED`. Retrying with the same `capture_session_id` is idempotent — no duplicates. Persistence is claimed only after read-back verification.

## Quick start

```bash
python scripts/flow_capture.py doctor
# Enterprise mode (authorization file configured by the harness):
python scripts/flow_capture.py capture --input examples/supplier-quote-comparison.json --db workflows.db
# Personal mode (explicit confirmation):
python scripts/flow_capture.py prepare --input examples/complaint-candidate.json --output confirmation.json --db workflows.db
python scripts/flow_capture.py confirm --confirmation confirmation.json --db workflows.db   # interactive terminal
python scripts/flow_capture.py commit --confirmation confirmation.json --db workflows.db
python scripts/flow_capture.py show --task-id <task-id> --db workflows.db
python scripts/flow_capture.py similar --task-type supplier-quote-comparison --db workflows.db
```

Storage is pluggable (`LOCAL_SQLITE` reference implementation, or an enterprise adapter provided at deployment). See [references/storage-adapter-contract.md](references/storage-adapter-contract.md) and [references/enterprise-authorization.md](references/enterprise-authorization.md).

## Requirements

Python 3.10+; no runtime packages outside the Python standard library.

## Installation

From a formal Release asset, extract the archive and run:

```bash
python enterprise-ai-workflow-capture/scripts/install.py --target <your-skills-directory>
```

The installer copies a self-contained skill and runs `doctor`. See [docs/INSTALL.md](docs/INSTALL.md) for acquisition, enterprise configuration, updates, backup and rollback.

## Development and verification

```bash
python -m unittest discover -s tests -v
python scripts/flow_capture.py doctor --db .tmp/acceptance.db
python scripts/build_release.py --version 2.0.0
```

See [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md) for the acceptance matrix, [docs/SECURITY.md](docs/SECURITY.md) for the threat boundaries, and [V2_TARGET_GAP_REPORT.md](V2_TARGET_GAP_REPORT.md) for the v1→v2 reconciliation.

## License

MIT. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
