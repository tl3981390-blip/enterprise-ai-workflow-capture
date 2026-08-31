#!/usr/bin/env python3
"""Install a self-contained copy of this skill into a chosen directory."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


EXCLUDE = {".git", ".pytest_cache", "__pycache__", "evidence", "dist"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    target = Path(args.target).resolve() / source.name
    if target.exists():
        if not args.replace:
            raise SystemExit(f"target already exists: {target}")
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(*EXCLUDE, "*.pyc", "*.db", "*.db-wal", "*.db-shm"))
    check = subprocess.run([sys.executable, str(target / "scripts" / "flow_capture.py"), "doctor"], text=True, capture_output=True)
    if check.returncode:
        shutil.rmtree(target, ignore_errors=True)
        raise SystemExit(check.stderr or check.stdout)
    manifest = []
    for path in sorted(p for p in target.rglob("*") if p.is_file()):
        manifest.append({"path": path.relative_to(target).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    print(json.dumps({"status": "installed", "target": str(target), "self_check": json.loads(check.stdout), "files": len(manifest)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

