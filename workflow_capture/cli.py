import argparse
import json
import sqlite3
import sys

from . import SCHEMA_VERSION, __version__
from .database import connect, migrate
from .errors import CaptureError
from .service import commit, load_json, prepare, save_json, show, similar


def output(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def build_parser():
    parser = argparse.ArgumentParser(prog="flow-capture", description="Capture confirmed human-AI work processes")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare", help="sanitize and prepare a human-confirmable draft")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p = commands.add_parser("commit", help="persist an explicitly confirmed draft")
    p.add_argument("--confirmation", required=True)
    p.add_argument("--token", required=True)
    p.add_argument("--db", required=True)
    p = commands.add_parser("show", help="read back one confirmed task")
    p.add_argument("--task-id", required=True)
    p.add_argument("--db", required=True)
    p = commands.add_parser("similar", help="find recent tasks with the same normalized task type")
    p.add_argument("--task-type", required=True)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--db", required=True)
    p = commands.add_parser("migrate", help="migrate a database to the supported schema")
    p.add_argument("--db", required=True)
    p = commands.add_parser("doctor", help="verify runtime and optional database health")
    p.add_argument("--db")
    return parser


def run(args):
    if args.command == "prepare":
        artifact = prepare(load_json(args.input))
        save_json(args.output, artifact)
        return {"status": artifact["status"], "output": args.output, **artifact["confirmation_summary"], "redactions": artifact["redactions"], "confirmation_token": artifact["confirmation_token"]}
    if args.command == "commit":
        return commit(load_json(args.confirmation), args.token, args.db)
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
        connection = connect(args.db)
        try:
            return {"status": "migrated", "schema_version": migrate(connection), "database": args.db}
        finally:
            connection.close()
    if args.command == "doctor":
        result = {"status": "ok", "package_version": __version__, "supported_schema_version": SCHEMA_VERSION, "sqlite_version": sqlite3.sqlite_version}
        if args.db:
            connection = connect(args.db)
            try:
                result["database_schema_version"] = migrate(connection)
                result["foreign_keys"] = bool(connection.execute("PRAGMA foreign_keys").fetchone()[0])
                result["integrity_check"] = connection.execute("PRAGMA integrity_check").fetchone()[0]
            finally:
                connection.close()
        return result
    raise CaptureError("unknown command")


def main(argv=None):
    try:
        args = build_parser().parse_args(argv)
        output(run(args))
        return 0
    except (CaptureError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except sqlite3.Error as exc:
        print(json.dumps({"status": "error", "error": "database operation failed", "detail": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

