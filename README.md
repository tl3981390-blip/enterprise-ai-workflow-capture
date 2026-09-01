# enterprise-ai-workflow-capture

A privacy-first enterprise Skill and deterministic local runtime that captures **how AI-assisted business tasks were actually completed** — as structured, sanitized, verifiable data.

It exists for the transition period before AI is deeply wired into business systems. The enterprise mandates: *when employees run these designated AI-assisted tasks, they invoke this Skill.* Employees keep working normally; the Skill turns "how this task was actually completed" into durable structured records — the raw material for later path comparison, SOP improvement, AI-usage improvement, automation-candidate discovery, and enterprise AI governance.

It is not a platform: no employee management, admin console, SSO, performance scoring, leaderboards, chat surveillance, data lake, or process-mining engine. And it is not passive monitoring: capture happens only because the employee invoked the Skill for a designated task.

## Two lawful capture modes

**ENTERPRISE_MANAGED_CAPTURE** — the harness signs a per-capture **HARNESS_CAPTURE_ASSERTION** (Ed25519); the runtime verifies it against the deployment-protected trust root and only then injects the capture session and harness-owned context. One low-friction command does validate → verify → inject → sanitize → persist → read-back. **Model data is not harness-trusted data**: the host model cannot mint assertions, select the trust root, or claim harness provenance — and unsigned or self-signed material fails closed. Local test minters exist (`scripts/make_test_grant.py`, `scripts/make_test_assertion.py`) but their output is mechanically stamped `DEVELOPMENT_TEST_ONLY` and refused under `PRODUCTION_ENTERPRISE`.

**PERSONAL_EXPLICIT_CAPTURE** — individuals keep the explicit flow: prepare, review the sanitized preview, confirm interactively, commit. The confirmation is a database-backed `PREPARED → CONFIRMED → CONSUMED` one-time transition bound to the exact payload hash.

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
# Enterprise mode (attested): the harness sets WORKFLOW_CAPTURE_ASSERTION + WORKFLOW_CAPTURE_TRUST_ROOT, then:
python scripts/flow_capture.py capture --input examples/supplier-quote-comparison-task-facts.json --db workflows.db
# Local test of the attested path (DEVELOPMENT_TEST_ONLY output):
python scripts/make_test_assertion.py --trust-root .tmp/trust-root.json --assertion .tmp/assertion.json \
    --issuer local-test-harness --session test-session-001 --task-types supplier-quote-comparison \
    --departments procurement --department procurement --workflow sourcing
WORKFLOW_CAPTURE_ASSERTION=.tmp/assertion.json WORKFLOW_CAPTURE_TRUST_ROOT=.tmp/trust-root.json \
    python scripts/flow_capture.py capture --input examples/supplier-quote-comparison-task-facts.json --db workflows.db
# Personal mode (explicit confirmation):
python scripts/flow_capture.py prepare --input examples/complaint-candidate.json --output confirmation.json --db workflows.db
python scripts/flow_capture.py confirm --confirmation confirmation.json --db workflows.db   # interactive terminal
python scripts/flow_capture.py commit --confirmation confirmation.json --db workflows.db
python scripts/flow_capture.py show --task-id <task-id> --db workflows.db
python scripts/flow_capture.py similar --task-type supplier-quote-comparison --db workflows.db
```

Storage is pluggable (`LOCAL_SQLITE` reference implementation, or an enterprise adapter provided at deployment). See [references/storage-adapter-contract.md](references/storage-adapter-contract.md) and [references/enterprise-authorization.md](references/enterprise-authorization.md).

## Requirements

Python 3.10+. Personal and development paths use only the Python standard library. Attested enterprise verification (Ed25519) requires the `cryptography` package (`pip install cryptography`, or the `enterprise` extra).

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
python scripts/check_release_hygiene.py --version 2.0.1
python scripts/build_release.py --version 2.0.1
```

See [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md) for the acceptance matrix, [docs/SECURITY.md](docs/SECURITY.md) for the threat boundaries, and [V2_TARGET_GAP_REPORT.md](V2_TARGET_GAP_REPORT.md) for the v1→v2 reconciliation.

## License

MIT. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
