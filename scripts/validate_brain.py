"""validate_brain.py – CI helper (referenced in ci.yml).

Validates the brain/ PARA vault:
  - brain/index.md must exist.
  - brain/log.md must exist.
  - brain/projects/, brain/areas/, brain/resources/, brain/archive/ must exist.
  - Each .md file must be valid UTF-8.

Exits 0 on success, 1 on any error.
"""

from __future__ import annotations

import sys
from pathlib import Path

REQUIRED_FILES = [
    "index.md",
    "log.md",
]

REQUIRED_DIRS = [
    "projects",
    "areas",
    "resources",
    "archive",
]


def validate_brain(brain_dir: Path) -> list[str]:
    errors: list[str] = []
    if not brain_dir.exists():
        return [f"brain/ directory not found at {brain_dir}"]

    for fname in REQUIRED_FILES:
        fp = brain_dir / fname
        if not fp.exists():
            errors.append(f"Missing required file: {fp}")

    for dname in REQUIRED_DIRS:
        dp = brain_dir / dname
        if not dp.exists() or not dp.is_dir():
            errors.append(f"Missing required directory: {dp}")

    # Validate all .md files are valid UTF-8
    for md_file in brain_dir.rglob("*.md"):
        try:
            md_file.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            errors.append(f"{md_file}: invalid UTF-8 — {e}")

    return errors


if __name__ == "__main__":
    repo_root = Path(__file__).parent.parent
    brain_dir = repo_root / "brain"
    errors = validate_brain(brain_dir)
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    md_count = len(list(brain_dir.rglob("*.md")))
    print(f"OK: brain/ vault validated ({md_count} markdown files).")
    sys.exit(0)
