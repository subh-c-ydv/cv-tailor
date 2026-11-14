"""Terminal batch mode (batch_processor.py)."""
import os

import pytest

import batch_processor
import utils


@pytest.fixture
def jds(tmp_path, monkeypatch, isolate):
    folder = tmp_path / "jds"
    folder.mkdir()
    monkeypatch.setattr(batch_processor, "JDS_DIR", str(folder))
    monkeypatch.setattr(batch_processor, "OUTPUTS_DIR", str(isolate))
    monkeypatch.setattr(batch_processor, "get_client", lambda: object())
    monkeypatch.setattr(utils, "read_cv_text", lambda: "CV")
    return folder


def _result(status, **extra):
    base = {"job_title": "PM", "company_name": "Acme", "stress_test": None, "keyword_score": 8,
            "status": status, "stop_reason": None, "output_dir": None, "jd_text": ""}
    base.update(extra)
    return base


def test_failed_jd_stays_in_inbox_and_others_are_archived(jds, monkeypatch, capsys):
    (jds / "a_good.txt").write_text("good role", encoding="utf-8")
    (jds / "b_broken.txt").write_text("boom", encoding="utf-8")
    (jds / "c_empty.txt").write_text("   ", encoding="utf-8")

    def fake_process(jd_text, cv_text, client):
        if "boom" in jd_text:
            raise RuntimeError("API overloaded")
        return _result("PASS")
    monkeypatch.setattr(batch_processor, "process_single_jd", fake_process)

    batch_processor.run_batch()

    assert sorted(os.listdir(jds)) == ["archive", "b_broken.txt", "c_empty.txt"]
    assert os.listdir(jds / "archive") == ["a_good.txt"]
    out = capsys.readouterr().out
    assert "API overloaded" in out and "The file is empty" in out and "1 passed" in out


def test_batch_summary_is_written_as_utf8(jds, monkeypatch, isolate):
    (jds / "role.txt").write_bytes("Konsulent – København".encode("cp1252"))
    seen = []

    def fake_process(jd_text, cv_text, client):
        seen.append(jd_text)
        return _result("PASS", job_title="Konsulent │ Lead", company_name="Ørsted")
    monkeypatch.setattr(batch_processor, "process_single_jd", fake_process)

    batch_processor.run_batch()

    assert seen == ["Konsulent – København"]
    summary_dir = isolate / "batch-summaries"
    (summary,) = os.listdir(summary_dir)
    assert "Konsulent │ Lead @ Ørsted" in (summary_dir / summary).read_text(encoding="utf-8")


def test_archive_does_not_overwrite(tmp_path):
    (tmp_path / "jd.txt").write_text("new", encoding="utf-8")
    (tmp_path / "archive").mkdir()
    (tmp_path / "archive" / "jd.txt").write_text("old", encoding="utf-8")
    batch_processor.archive_jd_file(str(tmp_path), "jd.txt")
    archived = os.listdir(tmp_path / "archive")
    assert len(archived) == 2 and "jd.txt" in archived


def test_gates_stop_before_documents(fake_client, monkeypatch):
    """Borderline and failing roles never reach CV generation in terminal batch mode."""
    import tailor_cv
    monkeypatch.setattr(tailor_cv, "main", lambda **kw: pytest.fail("CV should not be built"))

    stress_fail = fake_client('{"overall": "FAIL", "verdict": "No permit.", "parameters": []}')
    assert batch_processor.process_single_jd("JD", "CV", stress_fail)["status"] == "FAIL"

    low_keywords = fake_client('{"overall": "PASS", "verdict": "ok", "parameters": []}',
                               '{"score": 5, "matching_keywords": [], "missing_keywords": ["X"]}')
    result = batch_processor.process_single_jd("JD", "CV", low_keywords)
    assert result["status"] == "BORDERLINE" and result["missing_keywords"] == ["X"]
