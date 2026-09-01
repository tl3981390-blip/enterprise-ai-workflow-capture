import argparse
import json
import os
import sqlite3
import sys

from . import SCHEMA_VERSION, __version__
from .authorization import ENV_GRANT_FILE, load_grant
from .errors import AuthorizationError, CaptureError, CaptureStorageError, ConfirmationError
from .service import capture, commit, confirm, load_json, prepare, save_json, show, similar
from .storage import resolve_adapter


def output(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def build_parser():
    parser = argparse.ArgumentParser(prog="flow-capture", description="Capture human-AI work processes under explicit or enterprise-managed authorization")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("capture", help="enterprise-managed one-shot capture; requires harness-provided authorization and fails closed without it")
    p.add_argument("--input", required=True)
    p.add_argument("--db", help="local SQLite target; omit when the environment selects an enterprise storage adapter")
    p = commands.add_parser("prepare", help="sanitize and prepare a human-confirmable draft (personal explicit capture)")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--db", required=True)
    p = commands.add_parser("confirm", help="interactively confirm the exact prepared payload (personal explicit capture)")
    p.add_argument("--confirmation", required=True)
    p.add_argument("--db", required=True)
    p.add_argument("--identity")
    p.add_argument("--identity-source")
    p = commands.add_parser("commit", help="persist an explicitly confirmed draft")
    p.add_argument("--confirmation", required=True)
    p.add_argument("--db", required=True)
    p = commands.add_parser("show", help="read back one persisted task")
    p.add_argument("--task-id", required=True)
    p.add_argument("--db", required=True)
    p = commands.add_parser("similar", help="find recent tasks with the same normalized task type")
    p.add_argument("--task-type", required=True)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--db", required=True)
    p = commands.add_parser("migrate", help="migrate a database to the supported schema")
    p.add_argument("--db", required=True)
    p = commands.add_parser("doctor", help="verify runtime, storage and authorization configuration health")
    p.add_argument("--db")
    return parser


def run(args):
    if args.command == "capture":
        return capture(load_json(args.input), args.db)
    if args.command == "prepare":
        artifact = prepare(load_json(args.input), args.db)
        save_json(args.output, artifact)
        return {"status": artifact["status"], "output": args.output, "confirmation_id": artifact["confirmation_id"], "payload_hash": artifact["payload_hash"], **artifact["confirmation_summary"], "redactions": artifact["redactions"]}
    if args.command == "confirm":
        if bool(args.identity) != bool(args.identity_source):
            raise CaptureError("identity and identity-source must be supplied together")
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            raise ConfirmationError("human confirmation requires an interactive terminal; piped or automated confirmation is refused")
        artifact = load_json(args.confirmation)
        challenge = f"CONFIRM {artifact.get('payload_hash', '')[:12]}"
        print(json.dumps({"status": "HUMAN_CONFIRMATION_REQUIRED", "summary": artifact.get("confirmation_summary"), "payload_hash": artifact.get("payload_hash"), "type_exactly": challenge}, ensure_ascii=False, indent=2))
        response = input("> ")
        if response != challenge:
            raise ConfirmationError("confirmation challenge did not match")
        confirmed = confirm(artifact, args.db, method="interactive_tty", identity=args.identity, source=args.identity_source)
        save_json(args.confirmation, confirmed)
        return {"status": confirmed["status"], "confirmation_id": confirmed["confirmation_id"], "confirmed_at": confirmed["confirmed_at"], "confirmation_method": confirmed["confirmation_method"], "confirmation_identity": confirmed["confirmation_identity"], "confirmation_source": confirmed["confirmation_source"]}
    if args.command == "commit":
        return commit(load_json(args.confirmation), args.db)
    if args.command == "show":
        result = show(args.db, args.task_id)
        if result is None:
            raise CaptureError("task not found")
        return result
    if args.command == "similar":
        if not 1 <= args.limit <= 100:
            raise CaptureError("limit must be between 1 and 100")
        return {"task_type": args.task_type, "match_basis": "normalized_task_type", "results": similar(args.db, args.task_type, args.limit)}
    if args.command == "migrate":
        adapter = resolve_adapter(args.db)
        return {"status": "migrated", "schema_version": adapter.ensure_schema(), "database": args.db}
    if args.command == "doctor":
        result = {"status": "ok", "package_version": __version__, "supported_schema_version": SCHEMA_VERSION, "sqlite_version": sqlite3.sqlite_version}
        try:
            adapter = resolve_adapter(args.db)
            result["storage"] = {"kind": adapter.kind}
            if args.db:
                health = adapter.health()
                result["database_schema_version"] = health["schema_version"]
                result["foreign_keys"] = health["foreign_keys"]
                result["integrity_check"] = health["integrity_check"]
                chain = adapter.verify_evidence_chains()
                result["evidence_chain"] = chain
                if chain["status"] != "ok":
                    result["status"] = "error"
        except CaptureError as exc:
            result["storage"] = {"configured": False, "error": str(exc)}
            result["status"] = "error"
        result["authorization"] = {"configured": bool(os.environ.get(ENV_GRANT_FILE, "").strip())}
        if result["authorization"]["configured"]:
            try:
                grant = load_grant()
                result["authorization"].update({"mode": grant.mode, "issuer": grant.issuer, "verification": grant.verification, "expires_at": grant.data["expires_at"]})
            except AuthorizationError as exc:
                result["authorization"]["error"] = str(exc)
                result["status"] = "error"
        return result
    raise CaptureError("unknown command")


def main(argv=None):
    try:
        args = build_parser().parse_args(argv)
        result = run(args)
        output(result)
        return 1 if result.get("status") == "error" else 0
    except AuthorizationError as exc:
        print(json.dumps({"status": "CAPTURE_REFUSED_UNAUTHORIZED", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 4
    except CaptureStorageError as exc:
        print(json.dumps({"status": exc.status, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 5
    except (CaptureError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except sqlite3.Error as exc:
        print(json.dumps({"status": "error", "error": "database operation failed", "detail": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
