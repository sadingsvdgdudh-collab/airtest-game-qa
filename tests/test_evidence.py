import json

import pytest

from gameqa.bridge import TransientError
from gameqa.evidence import Evidence, write_report
from gameqa.__main__ import summarize


def test_retry_preserves_first_failure_and_marks_recovered_result(tmp_path):
    evidence = Evidence("QA-RETRY", tmp_path)
    calls = []
    def observation():
        calls.append(1)
        if len(calls) == 1:
            raise TransientError("recognition missed")
        return 42
    assert evidence.observe("read", observation) == 42
    assert evidence.data["unstable"] is True
    assert [row["outcome"] for row in evidence.data["steps"][0]["attempts"]] == ["failed", "passed"]
    with pytest.raises(AssertionError):
        evidence.observe("business assertion", lambda: evidence.check("gold", 5, 6, "rule"))
    assert len(evidence.data["steps"][1]["attempts"]) == 1


def test_action_is_never_retried(tmp_path):
    evidence = Evidence("QA-ACTION", tmp_path)
    count = []
    def purchase():
        count.append(1)
        raise TransientError("connection lost after send")
    with pytest.raises(TransientError):
        evidence.action("buy", purchase)
    assert len(count) == 1


def test_report_escapes_untrusted_game_text_and_redacts_secrets(tmp_path):
    evidence = Evidence("QA-REPORT", tmp_path / "QA-REPORT")
    evidence.data["diagnostics"] = {"password": "test-secret", "npc": "<script>alert(1)</script>"}
    evidence.data["outcome"] = "failed"
    write_report(tmp_path, [evidence.data])
    page = (tmp_path / "index.html").read_text()
    assert "<script>" not in page and "&lt;script&gt;" in page
    assert "test-secret" not in page
    assert json.loads((tmp_path / "report.json").read_text())["cases"][0]["diagnostics"]["password"] == "[redacted]"


def test_five_rounds_can_consistently_detect_fault_without_being_all_passed():
    rounds = [{"cases": [{"id": "SHOP-001", "outcome": "failed"}]} for _ in range(5)]
    result = summarize(rounds)
    assert result["consistent"] is True
    assert result["all_passed"] is False
    rounds[-1]["cases"][0]["outcome"] = "passed"
    assert summarize(rounds)["consistent"] is False


def test_skips_and_missing_rounds_cannot_claim_acceptance():
    assert summarize([{"cases": []}] * 5)["consistent"] is False
    assert summarize([{"cases": [{"id": "X", "outcome": "skipped"}]}] * 5)["consistent"] is False
    rounds = [{"cases": [{"id": "X", "outcome": "passed"}]}, {"cases": []}]
    assert summarize(rounds)["consistent"] is False
    assert summarize(rounds)["all_passed"] is False


def test_attachment_works_with_relative_report_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    evidence = Evidence("UI-001", "reports/UI-001")
    image = evidence.folder / "screen.png"
    image.write_bytes(b"image fixture")
    evidence.attach(image, "actual screenshot")
    assert evidence.data["attachments"][0]["path"] == "screen.png"
