"""Streamlit app flows, driven through Streamlit's AppTest harness with every
Claude call replaced by a fake."""
import os

import pytest
from streamlit.testing.v1 import AppTest

import generate_cover_letter
import keyword_match
import stress_test
import tailor_cv
import utils
from conftest import REPO_ROOT

APP_PATH = os.path.join(REPO_ROOT, "app.py")

PASS_REPORT = {"overall": "PASS", "verdict": "Good fit.", "parameters": [
    {"name": "Location", "result": "PASS", "reason": "Copenhagen"}]}


def keyword_report(score):
    return {"score": score, "matching_keywords": ["Agile"], "missing_keywords": ["SAFe"],
            "gaps": "No SAFe.", "recommendation": "Send"}


@pytest.fixture
def pipeline(monkeypatch):
    """Replace every slow or paid step with a fake. Returns a dict the test
    can tweak (e.g. the stress report) and inspect (calls made)."""
    state = {"stress": PASS_REPORT, "keyword_score": 8, "calls": []}

    monkeypatch.setattr(utils, "get_client", lambda: object())
    monkeypatch.setattr(utils, "read_cv_text", lambda: "CV TEXT")
    monkeypatch.setattr(stress_test, "run_stress_test",
                        lambda jd, client: state["calls"].append("stress") or state["stress"])
    monkeypatch.setattr(keyword_match, "run_keyword_match",
                        lambda jd, cv, client: state["calls"].append("keyword") or keyword_report(state["keyword_score"]))
    monkeypatch.setattr(utils, "extract_job_details", lambda jd, client: {
        "job_title": "Delivery Lead", "company_name": "Acme",
        "seniority_tier": "senior", "problem_specificity": "specific", "agency_posted": False})
    monkeypatch.setattr(tailor_cv, "extract_cv_sections",
                        lambda path, structure: {"header": ["Jane", "Tagline"], "tables": {}})

    def fake_tailor(sections, jd, client, structure, missing_keywords=None, gaps=None):
        state["calls"].append("tailor")
        state["tailor_inputs"] = (missing_keywords, gaps)
        return {"professional_summary": "S", "professional_experience": ["E"]}
    monkeypatch.setattr(tailor_cv, "tailor_with_claude", fake_tailor)

    def fake_build(sections, structure, tailored, title, company, output_dir):
        base = utils.cv_filename_base(title, company)
        paths = {"filename_base": base,
                 "cv_path": os.path.join(output_dir, base + ".docx"),
                 "cv_ats_path": os.path.join(output_dir, base + "_ATS.docx")}
        for key in ("cv_path", "cv_ats_path"):
            with open(paths[key], "wb") as f:
                f.write(b"docx")
        return paths
    monkeypatch.setattr(tailor_cv, "build_cv_documents", fake_build)

    def fake_letter(jd, cv, title, company, client, missing_keywords=None, gaps=None, shape=None, job_details=None):
        state["calls"].append("letter")
        state["letter_shape"] = shape
        return "Dear team,\n\nI'd like to apply."
    monkeypatch.setattr(generate_cover_letter, "generate_cover_letter", fake_letter)
    return state


def start(mode="Full Run", jd="A job description"):
    at = AppTest.from_file(APP_PATH, default_timeout=30).run()
    at.sidebar.radio[0].set_value(mode).run()
    at.text_area[0].input(jd).run()
    click(at, "▶ Run")
    return at


def click(at, label):
    next(b for b in at.button if b.label == label).click().run()


def page_ran_to_the_end(at):
    """st.exception() inside 'Technical details' is deliberate, so a crash is
    detected by the script stopping before the Batch Mode tab renders."""
    return any(t.value == "Batch Mode" for t in at.title)


def test_first_load_shows_input():
    at = AppTest.from_file(APP_PATH, default_timeout=30).run()
    assert not at.exception
    assert at.session_state.stage == "input"
    assert at.button[0].disabled is False or any(b.label == "▶ Run" for b in at.button)


def test_full_run_produces_cv_and_cover_letter(pipeline, isolate):
    at = start()
    assert not at.exception
    assert pipeline["calls"] == ["stress", "keyword", "tailor", "letter"]
    assert at.session_state.stage == "cover_letter"
    assert os.path.exists(at.session_state.cv_path)
    assert os.path.exists(at.session_state.cl_path)
    assert os.path.dirname(at.session_state.cl_path) == str(isolate / "Delivery Lead @ Acme")
    assert pipeline["tailor_inputs"] == (["SAFe"], "No SAFe.")
    assert pipeline["letter_shape"] in ("problem_first", "story_first", "question_led")  # senior/specific/direct row


def test_stress_fail_stops_before_documents(pipeline):
    pipeline["stress"] = {"overall": "FAIL", "verdict": "No work permit.", "parameters": []}
    at = start()
    assert pipeline["calls"] == ["stress"]
    assert any("No documents will be generated" in e.value for e in at.error)


def test_borderline_stress_waits_for_confirmation(pipeline):
    pipeline["stress"] = {"overall": "BORDERLINE", "verdict": "Salary unclear.", "parameters": []}
    at = start()
    assert pipeline["calls"] == ["stress"]
    click(at, "✅ Yes, proceed")
    assert "keyword" in pipeline["calls"]


@pytest.mark.parametrize("score, label", [(5, "moderate"), (2, "low")])
def test_weak_keyword_match_asks_before_continuing(pipeline, score, label):
    pipeline["keyword_score"] = score
    at = start()
    assert pipeline["calls"] == ["stress", "keyword"]
    assert any(label in w.value for w in at.warning)
    click(at, "❌ No, stop here")
    assert at.session_state.stage == "input"


def test_stress_test_only_borderline_ends_on_a_results_page(pipeline):
    pipeline["stress"] = {"overall": "BORDERLINE", "verdict": "Hmm.", "parameters": []}
    at = start(mode="Stress Test only")
    click(at, "✅ Yes, proceed")
    assert at.session_state.stage == "done"
    assert any(b.label.startswith("🔄 Start over") for b in at.button)
    assert pipeline["calls"] == ["stress"]


def test_failed_step_offers_retry_and_recovers(pipeline, monkeypatch):
    attempts = []

    def flaky(jd, client):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("The stress test response was cut off at the 2000-token limit.")
        return PASS_REPORT
    monkeypatch.setattr(stress_test, "run_stress_test", flaky)

    at = start(mode="Stress Test only")
    assert page_ran_to_the_end(at)
    assert any("Stress test failed" in e.value and "cut off" in e.value for e in at.error)
    assert at.session_state.stress_report is None

    click(at, "🔁 Try again")
    assert at.session_state.stress_report == PASS_REPORT


def test_failure_after_extraction_can_be_retried(pipeline, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("node exploded")
    monkeypatch.setattr(tailor_cv, "build_cv_documents", broken)

    at = start(mode="Tailor CV only")
    assert page_ran_to_the_end(at)
    assert any("Tailoring the CV failed" in e.value for e in at.error)
    assert at.session_state.cv_path is None


def test_sidebar_style_override_is_used(pipeline):
    at = AppTest.from_file(APP_PATH, default_timeout=30).run()
    at.sidebar.selectbox[0].set_value("Direct short").run()
    at.text_area[0].input("JD").run()
    click(at, "▶ Run")
    assert pipeline["letter_shape"] == "direct_short"
    assert "chosen manually" in at.session_state.cl_shape_reason


# --- Batch tab ---------------------------------------------------------------------

class Upload:
    def __init__(self, name, data):
        self.name, self._data = name, data

    def getvalue(self):
        return self._data


def test_batch_isolates_failures(monkeypatch, isolate):
    import importlib
    import app  # runs the script once in Streamlit's bare mode
    app = importlib.reload(app)

    def fake_process(jd_text, client, cv_text, shape_override=None):
        if "boom" in jd_text:
            raise RuntimeError("API overloaded")
        result = app.new_batch_result()
        result.update(job_title="PM", company_name="Acme", keyword_score=8)
        return result
    monkeypatch.setattr(app, "process_single_jd_ui", fake_process)
    monkeypatch.setattr(app, "get_client", lambda: object())
    monkeypatch.setattr(app, "read_cv_text", lambda: "CV")
    monkeypatch.setattr(app, "OUTPUTS_DIR", str(isolate))

    app.run_batch([Upload("a.txt", b"boom"),
                   Upload("b.txt", "Café role".encode("cp1252")),
                   Upload("c.txt", b"   ")])

    (summary,) = os.listdir(isolate / "batch-summaries")
    text = (isolate / "batch-summaries" / summary).read_text(encoding="utf-8")
    assert "FAIL       a.txt" in text and "API overloaded" in text
    assert "PASS       PM @ Acme  (keyword: 8/10)" in text
    assert "FAIL       c.txt" in text and "The file is empty" in text
    assert "Total: 3" in text
