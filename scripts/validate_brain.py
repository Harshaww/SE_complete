"""validate_brain.py - CI helper (referenced in ci.yml; PR-5, PR-10, SK-6.1).

Validates the brain/ PARA vault:
  - index.md and log.md exist; projects/, areas/, resources/, archive/ exist.
  - Every .md file is valid UTF-8.
  - Every note except index.md and log.md has frontmatter with title and type.
  - Every [[wikilink]] in a note (outside code) resolves to a note file name.
  - Every skill's "Cites brain note: [[x]]" resolves (SK-6.1).
  - At least MIN_RESEARCH_NOTES notes have type: research-note (PR-10).

Exits 0 on success, 1 on any error.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REQUIRED_FILES = ["index.md", "log.md"]
REQUIRED_DIRS = ["projects", "areas", "resources", "archive"]
NO_FRONTMATTER = {"index.md", "log.md"}
MIN_RESEARCH_NOTES = 10
REQUIRED_KEYS = ("title", "type")

_FENCE = re.compile(r"```.*?```", re.S)
_INLINE = re.compile(r"`[^`\n]*`")
_LINK = re.compile(r"\[\[([^\]]+)\]\]")
_CITES = re.compile(r"Cites brain note:\s*\[\[([^\]]+)\]\]")


def _frontmatter(text: str) -> dict[str, str] | None:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            out: dict[str, str] = {}
            for fm_line in lines[1:i]:
                if ":" in fm_line and not fm_line.startswith((" ", "\t")):
                    key, _, val = fm_line.partition(":")
                    out[key.strip()] = val.strip()
            return out
    return None


def _target(raw: str) -> str:
    return raw.split("|")[0].split("#")[0].strip()


def validate_brain(brain_dir: Path, skills_dir: Path | None = None) -> list[str]:
    errors: list[str] = []
    if not brain_dir.exists():
        return [f"brain/ directory not found at {brain_dir}"]

    for fname in REQUIRED_FILES:
        if not (brain_dir / fname).exists():
            errors.append(f"Missing required file: {brain_dir / fname}")
    for dname in REQUIRED_DIRS:
        dp = brain_dir / dname
        if not dp.exists() or not dp.is_dir():
            errors.append(f"Missing required directory: {dp}")

    texts: dict[Path, str] = {}
    for md_file in sorted(brain_dir.rglob("*.md")):
        try:
            texts[md_file] = md_file.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            errors.append(f"{md_file}: invalid UTF-8 - {e}")

    stems = {p.stem for p in texts}
    research = 0
    for path, text in texts.items():
        rel = path.relative_to(brain_dir)
        if path.name not in NO_FRONTMATTER or path.parent != brain_dir:
            fm = _frontmatter(text)
            if fm is None:
                errors.append(f"{rel}: missing frontmatter")
            else:
                for key in REQUIRED_KEYS:
                    if not fm.get(key):
                        errors.append(f"{rel}: frontmatter lacks '{key}'")
                if fm.get("type") == "research-note":
                    research += 1
        body = _INLINE.sub("", _FENCE.sub("", text))
        for raw in _LINK.findall(body):
            if _target(raw) not in stems:
                errors.append(f"{rel}: broken wikilink [[{raw}]]")

    if research < MIN_RESEARCH_NOTES:
        errors.append(f"PR-10: {research} research notes, need at least {MIN_RESEARCH_NOTES}")

    if skills_dir is not None and skills_dir.exists():
        for skill in sorted(skills_dir.glob("*/SKILL.md")):
            cited = _CITES.findall(skill.read_text(encoding="utf-8"))
            if not cited:
                errors.append(f"{skill}: cites no brain note (SK-6.1)")
            for raw in cited:
                if _target(raw) not in stems:
                    errors.append(f"{skill}: cites missing brain note [[{raw}]]")
    return errors


if __name__ == "__main__":
    repo_root = Path(__file__).parent.parent
    problems = validate_brain(repo_root / "brain", repo_root / "skills")
    if problems:
        for e in problems:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    md_count = len(list((repo_root / "brain").rglob("*.md")))
    print(f"OK: brain/ vault validated ({md_count} markdown files).")
    sys.exit(0)
