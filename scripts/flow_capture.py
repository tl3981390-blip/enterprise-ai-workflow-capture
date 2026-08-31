#!/usr/bin/env python3
"""Repository-local entrypoint; works without package installation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workflow_capture.cli import main


if __name__ == "__main__":
    raise SystemExit(main())

