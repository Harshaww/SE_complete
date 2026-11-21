"""The traceability matrix is complete and truthful (PR-4, TR-9, AGENTS.md rule on `# mark:`)."""

# mark: PR-4, TR-9
from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "traceability", Path(__file__).resolve().parents[2] / "scripts" / "traceability.py"
)
assert _SPEC and _SPEC.loader
trace = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(trace)


# mark: PR-4, TR-9
class TestTraceabilityMatrix:
    def test_repository_matrix_passes_its_own_checker(self, capsys):
        assert trace.main([]) == 0, capsys.readouterr().err

    def test_every_test_class_carries_a_mark(self):
        _, problems = trace.scan_tests()
        assert problems == []

    def test_unknown_requirement_in_a_mark_is_reported(self):
        reqs = {"FR-1.1": "x"}
        marks = {("FR-9.9", "tests/unit/test_x.py", "TestX"): None}
        problems = trace.check([{"requirement_id": "FR-1.1", "test_file": ""}], reqs, marks)
        assert any("unknown requirement FR-9.9" in p for p in problems)

    def test_requirement_without_test_or_inspection_is_reported(self):
        problems = trace.check([], {"FR-9.9": "x"}, {})
        assert any("no test mark and no INSPECTION entry" in p for p in problems)

    def test_stale_row_is_repaired_to_existing_class(self):
        rows = [
            {
                "requirement_id": "FR-1.1",
                "test_file": "tests/unit/test_normalise.py",
                "test_class": "TestGone",
                "test_name": "test_gone",
            }
        ]
        marks = {("FR-1.1", "tests/unit/test_normalise.py", "TestNormaliseVideoRef"): None}
        fixed = trace.repair_rows(rows, marks)
        assert fixed[0]["test_class"] == "TestNormaliseVideoRef" and fixed[0]["test_name"] == ""
