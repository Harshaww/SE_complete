"""scripts/redact_results.py strips secrets from live-run artifacts (NFR-SE-2, NFR-PV-1, TR-7)."""

# mark: NFR-SE-2, NFR-PV-1, TR-7
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "redact_results", Path(__file__).resolve().parents[2] / "scripts" / "redact_results.py"
)
assert _SPEC and _SPEC.loader
redact = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(redact)


# mark: NFR-SE-2
class TestRedactText:
    @pytest.mark.parametrize(
        "secret",
        [
            "ya29.a0AfH6SMBexampleexampleexample",
            "1//0gExampleRefreshTokenValue_abcdef-123",
            "AIzaSyExampleExampleExampleExample12345",  # gitleaks:allow
            "GOCSPX-ExampleSecretValue12",
            "123456789012-abcdefghijklmnopqrstuvwx.apps.googleusercontent.com",
            "Authorization: Bearer abcdefghijklmnop.1234",
            "eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.SflKxwRJSMeKKF2QT4",
            "someone@example.com",
            "UCuAXFkgsw1L7xaCfnd5JJOw",
        ],
    )
    def test_known_shapes_removed(self, secret):
        out = redact.redact_text(f"before {secret} after", env={})
        assert secret not in out and redact.REDACTED in out
        assert out.startswith("before ") and out.endswith(" after")

    def test_env_values_removed_even_when_unrecognisable(self):
        env = {"CEREBRA_REFRESH_TOKEN": "totally-custom-value-123"}
        out = redact.redact_text("token=totally-custom-value-123;", env=env)
        assert "totally-custom-value-123" not in out

    def test_short_env_values_ignored_to_avoid_mangling_text(self):
        out = redact.redact_text("pass test ok", env={"GOOGLE_CLIENT_ID": "ok"})
        assert out == "pass test ok"

    def test_clean_text_unchanged(self):
        text = "tests/integration/test_live_readonly.py::test_x PASSED in 1.2s"
        assert redact.redact_text(text, env={}) == text


# mark: NFR-SE-2, TR-5
class TestRedactFiles:
    def test_file_rewritten_in_place(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CEREBRA_REFRESH_TOKEN", "env-secret-value-xyz")
        xml = tmp_path / "live-results.xml"
        xml.write_text(
            '<testsuite><testcase name="a"><failure message="ya29.leakedleakedleaked '
            'env-secret-value-xyz"/></testcase></testsuite>',
            encoding="utf-8",
        )
        assert redact.main([str(xml)]) == 0
        cleaned = xml.read_text(encoding="utf-8")
        assert "ya29." not in cleaned and "env-secret-value-xyz" not in cleaned
        assert '<testcase name="a">' in cleaned  # structure preserved

    def test_missing_file_is_error(self, tmp_path, capsys):
        assert redact.main([str(tmp_path / "nope.xml")]) == 1
        assert "cannot process" in capsys.readouterr().err

    def test_no_args_is_usage_error(self, capsys):
        assert redact.main([]) == 1
        assert "usage" in capsys.readouterr().err
