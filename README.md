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
python scripts/flow_capture.py prepare --input examples/complaint-candidate.json --output confirmation.json --db workflows.db
# Review, then the human runs this in an interactive terminal:
python scripts/flow_capture.py confirm --confirmation confirmation.json --db workflows.db
python scripts/flow_capture.py commit --confirmation confirmation.json --db workflows.db
python scripts/flow_capture.py show --task-id <task-id> --db workflows.db
python scripts/flow_capture.py similar --task-type customer-complaint-response --db workflows.db
```

Prepare exposes no commit token. Confirmation is a separate interactive state transition stored in the database and consumed atomically by Commit.

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
python scripts/build_release.py --version 1.0.1
```

See [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md) for the acceptance matrix and [docs/SECURITY.md](docs/SECURITY.md) for the threat boundaries.

## License

MIT. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
