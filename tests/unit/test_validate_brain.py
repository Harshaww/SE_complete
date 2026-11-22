"""Tests for scripts/validate_brain.py (PR-5, PR-10, SK-6.1)."""

# mark: PR-5, PR-10, SK-6.1, TR-1
from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "validate_brain", Path(__file__).parents[2] / "scripts" / "validate_brain.py"
)
assert _SPEC and _SPEC.loader
vb = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(vb)


def _vault(tmp_path: Path, notes: int = 10) -> Path:
    b = tmp_path / "brain"
    for d in ("projects", "areas", "resources", "archive"):
        (b / d).mkdir(parents=True)
    (b / "index.md").write_text("# Index\n", encoding="utf-8")
    (b / "log.md").write_text("# Log\n", encoding="utf-8")
    for i in range(notes):
        (b / "resources" / f"n{i}.md").write_text(
            f"---\ntitle: N{i}\ntype: research-note\n---\n\nBody.\n", encoding="utf-8"
        )
    return b


def test_valid_vault_passes(tmp_path: Path) -> None:
    assert vb.validate_brain(_vault(tmp_path)) == []


def test_too_few_research_notes(tmp_path: Path) -> None:
    errs = vb.validate_brain(_vault(tmp_path, notes=3))
    assert any("PR-10" in e for e in errs)


def test_missing_frontmatter_and_broken_link(tmp_path: Path) -> None:
    b = _vault(tmp_path)
    (b / "resources" / "bad.md").write_text("No frontmatter [[nowhere]]\n", encoding="utf-8")
    errs = vb.validate_brain(b)
    assert any("missing frontmatter" in e for e in errs)
    assert any("broken wikilink [[nowhere]]" in e for e in errs)


def test_links_in_code_and_aliases_handled(tmp_path: Path) -> None:
    b = _vault(tmp_path)
    (b / "resources" / "ok.md").write_text(
        "---\ntitle: Ok\ntype: note\n---\n\n`[[example]]` and [[n1|alias]] and [[n2#h]]\n"
        "```\n[[fenced]]\n```\n",
        encoding="utf-8",
    )
    assert vb.validate_brain(b) == []


def test_skill_citation_must_resolve(tmp_path: Path) -> None:
    b = _vault(tmp_path)
    s = tmp_path / "skills" / "demo"
    s.mkdir(parents=True)
    (s / "SKILL.md").write_text(
        "---\nname: demo\n---\nCites brain note: [[ghost]].\n", encoding="utf-8"
    )
    errs = vb.validate_brain(b, tmp_path / "skills")
    assert any("ghost" in e for e in errs)
    (s / "SKILL.md").write_text(
        "---\nname: demo\n---\nCites brain note: [[n1]].\n", encoding="utf-8"
    )
    assert vb.validate_brain(b, tmp_path / "skills") == []
