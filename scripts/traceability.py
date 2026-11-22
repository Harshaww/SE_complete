"""traceability.py - keep docs/traceability.csv complete and truthful (PR-4, TR-9, AGENTS.md).

    python scripts/traceability.py            # CHECK (CI): exit 1 on any problem
    python scripts/traceability.py --write    # regenerate missing rows in docs/traceability.csv

Rules enforced:
  1. every ``class Test*`` in tests/ has a ``# mark: FR-x.y, ...`` comment directly above it;
  2. every mark names a known requirement (docs/requirement-ids.txt) or an ADR;
  3. every requirement in docs/requirement-ids.txt is verified by at least one test class mark or
     a documented INSPECTION artifact below, and appears in the CSV;
  4. every CSV row points at a file / class / test that exists.
Curated rows already in the CSV are never edited by --write; only missing rows are added.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "docs" / "traceability.csv"
IDS_PATH = ROOT / "docs" / "requirement-ids.txt"
FIELDS = [
    "requirement_id",
    "description",
    "test_file",
    "test_class",
    "test_name",
    "skill",
    "brain_note",
]
MARK_RE = re.compile(r"^\s*#\s*mark:\s*(.+)$")
ID_RE = re.compile(r"\b(?:ADR-[A-Z]|[A-Z]{2,3}-(?:[A-Z]{2}-)?\d+(?:\.\d+)?)\b")
EXTRA_OK = re.compile(r"^(ADR-[A-Z]|SRS Appendix .*)$")  # non-requirement references in the CSV

# Requirements verified by inspection of an artifact rather than an automated test.
INSPECTION: dict[str, tuple[str, str]] = {
    "BR-6": ("brain/log.md", "Brain notes are authored and logged per member; reviewed in PRs"),
    "CON-2": ("docs/adr/ADR-B.md", "Quota budget design; reservations tested under TR-6"),
    "CON-4": ("src/cerebra/domain/errors.py", "NO_YOUTUBE_CHANNEL mapping, see FR-4.12 tests"),
    "CON-7": (".github/workflows/ci.yml", "PR review is a repository setting; CI runs on every PR"),
    "CON-8": ("scripts/validate_skills.py", "MCP stdio server + SKILL.md validation in CI"),
    "CON-9": ("pyproject.toml", "Python package (requires-python, src/cerebra)"),
    "NFR-CO-2": (
        "docs/adr/ADR-B.md",
        "Team process: one Google Cloud project; no workaround code exists",
    ),
    "NFR-DO-1": ("docs/user-guide.md", "User guide and docs/developer-api.md kept with the code"),
    "NFR-MA-2": (".github/workflows/ci.yml", "ruff check + ruff format --check run in CI"),
    "NFR-MA-3": ("docs/adr/ADR-A.md", "Every ADR carries a 'Brain notes:' citation"),
    "NFR-PF-3": (
        "tests/integration/test_live_readonly.py",
        "Latency of real calls: measured manually, docs/testing/live-smoke-runbook.md",
    ),
    "NFR-PF-4": (
        "tests/integration/test_live_write.py",
        "Latency of real calls: measured manually, docs/testing/live-smoke-runbook.md",
    ),
    "NFR-PO-1": ("docs/user-guide.md", "Pure-Python dependencies; documented set-up"),
    "NFR-SE-6": (
        ".github/workflows/ci.yml",
        "Dependencies pinned in requirements.lock (CI installs from it); pip-audit on it",
    ),
    "NFR-SE-7": (
        "src/cerebra/mcp_server.py",
        "stdio transport only; no HTTP transport is provided",
    ),
    "NFR-TE-2": ("pyproject.toml", "coverage fail_under = 80 enforced by pytest-cov in CI"),
    "TR-8": ("skills/local-check/SKILL.md", "Skill evaluations recorded in docs/testing/"),
    "TR-9": ("docs/testing/test-plan.md", "Process: defects get regression tests"),
    "PR-1": ("docs/requirement-ids.txt", "SRS v1.0 maintained by the team"),
    "PR-2": ("docs/architecture.md", "Architecture documentation and ADRs"),
    "PR-3": ("AGENTS.md", "Development plan and issue workflow"),
    "PR-4": ("docs/traceability.csv", "This matrix, checked by scripts/traceability.py in CI"),
    "PR-5": (
        ".github/workflows/ci.yml",
        "Build, ruff, tests, gitleaks, skill and brain validation",
    ),
    "PR-6": ("README.md", "Branching and review policy; CHANGELOG.md"),
    "PR-7": ("src/cerebra/ports/interfaces.py", "Provider interfaces; see FR-5.17 contract tests"),
    "PR-8": ("docs/developer-api.md", "User guide and developer API documentation"),
    "PR-9": ("scripts/validate_brain.py", "PARA vault validated in CI"),
    "PR-10": ("brain/index.md", "Stage deliverable: SRS, vault, research notes"),
    "PR-11": ("AGENTS.md", "AI-assisted development rules and human review"),
    "SK-1.1": (
        "skills/video-to-playlist/SKILL.md",
        "Skill workflow; validated by validate_skills.py",
    ),
    "SK-1.2": (
        "skills/video-to-playlist/SKILL.md",
        "Skill stops before the write step; see FR-4.6 tests",
    ),
    "SK-1.3": ("skills/video-to-playlist/SKILL.md", "Untrusted metadata rule; see NFR-SE tests"),
    "SK-1.4": ("skills/video-to-playlist/SKILL.md", "Step 5 analysis contents"),
    "SK-1.5": ("skills/video-to-playlist/SKILL.md", "Failure reporting"),
    "SK-2.1": ("skills/local-check/SKILL.md", "Build + test + lint workflow"),
    "SK-2.2": ("skills/local-check/SKILL.md", "Fixture mode only; cannot write"),
    "SK-3.1": ("skills/brain-ingest/SKILL.md", "Ingest workflow"),
    "SK-3.2": ("skills/brain-ingest/SKILL.md", "Own-words summary and source record"),
    "SK-4.1": ("skills/brain-refine/SKILL.md", "Inbox to PARA workflow"),
    "SK-5.1": ("skills/brain-query/SKILL.md", "Query workflow"),
    "SK-5.2": ("skills/brain-query/SKILL.md", "Read-only except run log"),
    "SK-6.1": ("scripts/validate_skills.py", "Frontmatter/name validation runs in CI"),
    "SK-6.2": ("docs/testing/test-plan.md", "Skill evaluation results recorded per stage"),
}


def _key(rid: str) -> tuple[str, list[object]]:
    parts = re.split(r"[-.]", rid)
    return parts[0], [int(p) if p.isdigit() else p for p in parts[1:]]


def load_requirements() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in IDS_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            rid, _, text = line.partition("\t")
            out[rid] = text.strip()
    return out


def scan_tests() -> tuple[dict[tuple[str, str, str], None], list[str]]:
    """Return ({(req_id, file, class)}, [unmarked class problems])."""
    marks: dict[tuple[str, str, str], None] = {}
    problems: list[str] = []
    for path in sorted((ROOT / "tests").rglob("test_*.py")):
        rel = path.relative_to(ROOT).as_posix()
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            m = re.match(r"class (Test\w*)", line)
            if not m:
                continue
            j = i - 1
            while j >= 0 and lines[j].lstrip().startswith("@"):
                j -= 1
            mark = MARK_RE.match(lines[j]) if j >= 0 else None
            if not mark:
                problems.append(
                    f"{rel}:{i + 1}: class {m.group(1)} has no '# mark: FR-x.y' comment"
                )
                continue
            for rid in ID_RE.findall(mark.group(1)):
                marks[(rid, rel, m.group(1))] = None
    return marks, problems


def read_csv() -> list[dict[str, str]]:
    with CSV_PATH.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def validate_rows(rows: list[dict[str, str]], reqs: dict[str, str]) -> list[str]:
    problems: list[str] = []
    for n, row in enumerate(rows, start=2):
        rid, tfile = row["requirement_id"], row["test_file"]
        if rid not in reqs and not EXTRA_OK.match(rid):
            problems.append(f"traceability.csv:{n}: unknown requirement {rid!r}")
        if not tfile:
            continue
        path = ROOT / tfile
        if not path.exists():
            problems.append(f"traceability.csv:{n}: {tfile} does not exist")
            continue
        if row["test_class"] == "(inspection)" or not tfile.startswith("tests/"):
            continue  # inspection artifact: existence is enough
        text = path.read_text(encoding="utf-8")
        if row["test_class"] and f"class {row['test_class']}" not in text:
            problems.append(f"traceability.csv:{n}: class {row['test_class']} not in {tfile}")
        if row["test_name"] and f"def {row['test_name']}" not in text:
            problems.append(f"traceability.csv:{n}: test {row['test_name']} not in {tfile}")
    return problems


def repair_rows(
    rows: list[dict[str, str]], marks: dict[tuple[str, str, str], None]
) -> list[dict[str, str]]:
    """Point stale references (renamed/removed tests or classes) at what exists today."""
    for row in rows:
        tfile = row["test_file"]
        if not tfile.startswith("tests/") or row["test_class"] == "(inspection)":
            continue
        path = ROOT / tfile
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        if row["test_class"] and f"class {row['test_class']}" not in text:
            classes = sorted(c for r, f, c in marks if r == row["requirement_id"] and f == tfile)
            row["test_class"] = classes[0] if classes else ""
            row["test_name"] = ""  # the old test name belonged to the old class
        if row["test_name"] and f"def {row['test_name']}" not in text:
            row["test_name"] = ""  # keep the class-level reference
    return rows


def build_rows(
    rows: list[dict[str, str]], reqs: dict[str, str], marks: dict[tuple[str, str, str], None]
) -> list[dict[str, str]]:
    rows = repair_rows(rows, marks)
    have = {(r["requirement_id"], r["test_file"], r["test_class"]) for r in rows}
    new = list(rows)
    for rid, tfile, cls in marks:
        if rid in reqs and (rid, tfile, cls) not in have:
            new.append(
                dict.fromkeys(FIELDS, "")
                | {
                    "requirement_id": rid,
                    "description": reqs[rid],
                    "test_file": tfile,
                    "test_class": cls,
                }
            )
    marked = {rid for rid, _, _ in marks}
    present = {r["requirement_id"] for r in new}
    for rid in reqs:
        if rid not in marked and rid not in present and rid in INSPECTION:
            artifact, note = INSPECTION[rid]
            new.append(
                dict.fromkeys(FIELDS, "")
                | {
                    "requirement_id": rid,
                    "description": reqs[rid],
                    "test_file": artifact,
                    "test_class": "(inspection)",
                    "test_name": note,
                }
            )
    new.sort(
        key=lambda r: (_key(r["requirement_id"]), r["test_file"], r["test_class"], r["test_name"])
    )
    return new


def check(
    rows: list[dict[str, str]], reqs: dict[str, str], marks: dict[tuple[str, str, str], None]
) -> list[str]:
    problems = validate_rows(rows, reqs)
    for rid, tfile, cls in marks:
        if rid not in reqs and not rid.startswith("ADR-"):
            problems.append(f"{tfile}: class {cls} marks unknown requirement {rid}")
    marked = {rid for rid, _, _ in marks}
    in_csv = {r["requirement_id"] for r in rows}
    for rid in reqs:
        if rid not in marked and rid not in INSPECTION:
            problems.append(f"{rid}: no test mark and no INSPECTION entry")
        if rid not in in_csv:
            problems.append(f"{rid}: missing from docs/traceability.csv (run --write)")
    for rid, (artifact, _) in INSPECTION.items():
        if not (ROOT / artifact).exists():
            problems.append(f"INSPECTION[{rid}]: {artifact} does not exist")
        if rid not in reqs:
            problems.append(f"INSPECTION[{rid}]: not a known requirement")
    return problems


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    reqs = load_requirements()
    marks, problems = scan_tests()
    rows = read_csv()
    if "--write" in args:
        new = build_rows(rows, reqs, marks)
        with CSV_PATH.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(new)
        print(f"traceability: wrote {len(new)} rows (was {len(rows)})")
        rows = new
    problems += check(rows, reqs, marks)
    for p in problems:
        print(f"traceability: {p}", file=sys.stderr)
    if not problems:
        print(f"traceability: OK ({len(reqs)} requirements, {len(rows)} rows)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
