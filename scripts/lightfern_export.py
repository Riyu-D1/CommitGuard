#!/usr/bin/env python3
"""Export the company brain into the Lightfern app folder.

Writes <app>/brain/company_brain.json (verbatim) and one markdown file per
policy under <app>/brain/policies/ — that's what the Lightfern app's Brain
panel lists and what Lightfern's assistant can read. The real work lives in
backend/lightfern_bridge.export_brain so the bridge re-exports identically.

Usage:
    uv run python scripts/lightfern_export.py [app_dir]

Defaults to lightfern/CommitGuard Brain in this repo.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import lightfern_bridge  # noqa: E402

DEFAULT_APP = ROOT / "lightfern" / "CommitGuard Brain"


def main() -> int:
    app_dir = Path(sys.argv[1]).expanduser().resolve() \
        if len(sys.argv) > 1 else DEFAULT_APP
    ok = lightfern_bridge.export_brain(app_dir=app_dir)
    if not ok:
        print(f"export FAILED -> {app_dir}", file=sys.stderr)
        return 1
    n = len(list((app_dir / "brain" / "policies").glob("*.md")))
    print(f"exported -> {app_dir / 'brain'} ({n} policy files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
