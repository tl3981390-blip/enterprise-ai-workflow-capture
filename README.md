# enterprise-ai-workflow-capture

A privacy-first Codex Skill and deterministic local runtime for capturing **how human + AI work was actually completed**.

It is not a transcript archive, surveillance system, AI usage counter, employee scoring system, or autonomous process-mining platform. A record is created only after an employee explicitly invokes the Skill, reviews the sanitized candidate, and confirms it.

## What v1 records

- task goal, prerequisites and result adoption state;
- ordered human, AI, tool and system actions;
- clarification, correction, retry, failure and recovery events;
- minimal sanitized evidence with a tamper-evident hash chain;
- stable UUID business identifiers, lineage and optional hashed business references;
- schema/event versions that survive host and database migration.

Derived knowledge is deliberately separate. v1 stores enough lineage to compare paths later, but it never equates “fewest turns” with “best” and never promotes a `BEST_KNOWN_PATH` automatically.

## Requirements

Python 3.10+; no runtime packages outside the Python standard library.

## Quick start

```bash
python scripts/flow_capture.py doctor
python scripts/flow_capture.py prepare --input examples/complaint-candidate.json --output confirmation.json
# Review confirmation.json and explicitly confirm in the current interaction.
python scripts/flow_capture.py commit --confirmation confirmation.json --token <shown-token> --db workflows.db
python scripts/flow_capture.py show --task-id <task-id> --db workflows.db
python scripts/flow_capture.py similar --task-type customer-complaint-response --db workflows.db
```

The confirmation token proves only that the exact prepared artifact is being committed; it does not substitute for the human's explicit confirmation.

## Installation

From a formal Release asset, extract the archive and run:

```bash
python enterprise-ai-workflow-capture/scripts/install.py --target <your-skills-directory>
```

The installer copies a self-contained skill and runs `doctor`. See [docs/INSTALL.md](docs/INSTALL.md) for acquisition, updates, backup and rollback.

## Development and verification

```bash
python -m unittest discover -s tests -v
python scripts/flow_capture.py doctor --db .tmp/acceptance.db
python <skill-creator>/scripts/quick_validate.py .
python scripts/build_release.py --version 1.0.0
```

See [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md) for the acceptance matrix and [docs/SECURITY.md](docs/SECURITY.md) for the threat boundaries.

## License

MIT. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

