#!/usr/bin/env python3
import argparse
import hashlib
import shutil
import tempfile
import zipfile
from pathlib import Path


EXCLUDE_PARTS = {".git", ".pytest_cache", ".tmp", "__pycache__", "evidence", "dist", ".mimosa"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--output-dir", default="dist")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    name = f"enterprise-ai-workflow-capture-v{args.version}.zip"
    asset = output / name
    with tempfile.TemporaryDirectory() as temp:
        stage = Path(temp) / "enterprise-ai-workflow-capture"
        shutil.copytree(root, stage, ignore=shutil.ignore_patterns(*EXCLUDE_PARTS, "*.pyc", "*.db", "*.db-wal", "*.db-shm"))
        with zipfile.ZipFile(asset, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(p for p in stage.rglob("*") if p.is_file()):
                info = zipfile.ZipInfo(path.relative_to(stage.parent).as_posix(), (2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, path.read_bytes())
    checksum = hashlib.sha256(asset.read_bytes()).hexdigest()
    sums = output / "SHA256SUMS.txt"
    sums.write_text(f"{checksum}  {name}\n", encoding="ascii")
    print(f"{asset}\n{checksum}")


if __name__ == "__main__":
    main()
