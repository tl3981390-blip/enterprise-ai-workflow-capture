#!/usr/bin/env python3
"""Release hygiene check: SKILL.md strict frontmatter + harness discovery.

Mechanical checks that the packaged skill is discoverable and well-formed:

1. SKILL.md frontmatter strictly YAML-parses; ``name`` matches the repository
   skill name; ``metadata.version`` equals the expected version; description
   present; the document body starts only after the frontmatter block.
2. Discovery: under the given skills directory, exactly one SKILL.md declares
   this skill's name (no duplicates, no absence).

Usage:
    python scripts/check_release_hygiene.py --version 2.0.1 [--skills-dir DIR]
"""

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

SKILL_NAME = "enterprise-ai-workflow-capture"


def check_skill_md(root, expected_version, errors):
    skill_md = root / "SKILL.md"
    if not skill_md.is_file():
        errors.append("SKILL.md missing")
        return
    text = skill_md.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not match:
        errors.append("SKILL.md has no strict frontmatter block")
        return
    try:
        frontmatter = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        errors.append(f"SKILL.md frontmatter is not valid YAML: {exc}")
        return
    if not isinstance(frontmatter, dict):
        errors.append("SKILL.md frontmatter is not a YAML mapping")
        return
    if frontmatter.get("name") != SKILL_NAME:
        errors.append(f"SKILL.md name is {frontmatter.get('name')!r}, expected {SKILL_NAME!r}")
    version = str((frontmatter.get("metadata") or {}).get("version", ""))
    if version != expected_version:
        errors.append(f"SKILL.md metadata.version is {version!r}, expected {expected_version!r}")
    if not str(frontmatter.get("description", "")).strip():
        errors.append("SKILL.md description is empty")
    body = match.group(2)
    if not body.strip():
        errors.append("SKILL.md body is empty")
    if re.search(r"^metadata:", body, re.M):
        errors.append("SKILL.md body appears to contain frontmatter metadata")


def check_discovery(skills_dir, errors):
    found = []
    for path in skills_dir.rglob("SKILL.md"):
        text = path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if not match:
            continue
        try:
            frontmatter = yaml.safe_load(match.group(1))
        except yaml.YAMLError:
            continue
        if isinstance(frontmatter, dict) and frontmatter.get("name") == SKILL_NAME:
            found.append(path)
    if len(found) != 1:
        errors.append(f"discovery expects exactly 1 installed skill named {SKILL_NAME!r}, found {len(found)}")


def main():
    parser = argparse.ArgumentParser(description="Release hygiene: SKILL.md frontmatter + discovery check")
    parser.add_argument("--version", required=True)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--skills-dir")
    args = parser.parse_args()
    errors = []
    check_skill_md(Path(args.root), args.version, errors)
    if args.skills_dir:
        check_discovery(Path(args.skills_dir), errors)
    print(json.dumps({"status": "PASS" if not errors else "FAIL", "errors": errors}, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
