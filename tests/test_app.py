"""Streamlit app flows, driven through Streamlit's AppTest harness with every
Claude call replaced by a fake (see fake_pipeline in conftest.py)."""
import os

import pytest
from streamlit.testing.v1 import AppTest

import pipeline
import stress_test
import tailor_cv
from conftest import PASS_REPORT, REPO_ROOT

APP_PATH = os.path.join(REPO_ROOT, "app.py")


def new_app():
    return AppTest.from_file(APP_PATH, default_timeout=30)


def start(mode="Full Run", jd="A job description"):
    at = new_app().run()
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


# --- Single JD ------------------------------------------------------------------------

def test_first_load_shows_input():
    at = new_app().run()
    assert not at.exception
    assert at.session_state.stage == "input"
    assert any(b.label == "▶ Run" for b in at.button)


def test_full_run_produces_cv_and_cover_letter(fake_pipeline, isolate):
    at = start()
    assert not at.exception
    assert fake_pipeline["calls"] == ["stress", "keyword", "details", "tailor", "letter"]
    assert at.session_state.stage == "cover_letter"
    output_dir = isolate / "Delivery Lead @ Acme"
    assert os.path.exists(at.session_state.cv["cv_path"])
    assert os.path.dirname(at.session_state.letter["path"]) == str(output_dir)
    assert (output_dir / "keyword_match_report.txt").exists()
    assert fake_pipeline["tailor_inputs"] == (["SAFe"], "No SAFe.")
    assert fake_pipeline["letter_shape"] in ("problem_first", "story_first", "question_led")  # senior/specific/direct row


def test_stress_fail_stops_before_documents(fake_pipeline):
    fake_pipeline["stress"] = {"overall": "FAIL", "verdict": "No work permit.", "parameters": []}
    at = start()
    assert fake_pipeline["calls"] == ["stress"]
    assert any("No documents will be generated" in e.value for e in at.error)


def test_borderline_stress_waits_for_confirmation(fake_pipeline):
    fake_pipeline["stress"] = {"overall": "BORDERLINE", "verdict": "Salary unclear.", "parameters": []}
    at = start()
    assert fake_pipeline["calls"] == ["stress"]
    click(at, "✅ Yes, proceed")
    assert "keyword" in fake_pipeline["calls"]


@pytest.mark.parametrize("score, label", [(5, "moderate"), (2, "low")])
def test_weak_keyword_match_asks_before_continuing(fake_pipeline, score, label):
    fake_pipeline["keyword_score"] = score
    at = start()
    assert fake_pipeline["calls"] == ["stress", "keyword"]
    assert any(label in w.value for w in at.warning)
    click(at, "❌ No, stop here")
    assert at.session_state.stage == "input"


def test_stress_test_only_borderline_ends_on_a_results_page(fake_pipeline):
    fake_pipeline["stress"] = {"overall": "BORDERLINE", "verdict": "Hmm.", "parameters": []}
    at = start(mode="Stress Test only")
    click(at, "✅ Yes, proceed")
    assert at.session_state.stage == "done"
    assert any(b.label.startswith("🔄 Start over") for b in at.button)
    assert fake_pipeline["calls"] == ["stress"]


def test_cover_letter_only_skips_the_checks(fake_pipeline):
    at = start(mode="Cover Letter only")
    assert fake_pipeline["calls"] == ["details", "letter"]
    assert at.session_state.cv is None and os.path.exists(at.session_state.letter["path"])


def test_failed_step_offers_retry_and_recovers(fake_pipeline, monkeypatch):
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


def test_failure_after_extraction_can_be_retried(fake_pipeline, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("node exploded")
    monkeypatch.setattr(tailor_cv, "build_cv_documents", broken)

    at = start(mode="Tailor CV only")
    assert page_ran_to_the_end(at)
    assert any("Tailoring the CV failed" in e.value for e in at.error)
    assert at.session_state.cv is None


def test_sidebar_style_override_is_used(fake_pipeline):
    at = new_app().run()
    at.sidebar.selectbox[0].set_value("Direct short").run()
    at.text_area[0].input("JD").run()
    click(at, "▶ Run")
    assert fake_pipeline["letter_shape"] == "direct_short"
    assert at.session_state.letter["shape_reason"] == "chosen manually"


# --- Batch tab --------------------------------------------------------------------------
# AppTest can't drive the file uploader, so the batch is processed with the
# real pipeline (and fake steps), then handed to the app as session state.

@pytest.fixture
def batch(fake_pipeline):
    results = [pipeline.process_batch_item("a_pass.txt", b"JD", "CV", object())]
    fake_pipeline["keyword_score"] = 5
    results.append(pipeline.process_batch_item("b_held.txt", b"JD", "CV", object()))
    results.append(pipeline.process_batch_item("c_empty.txt", b" ", "CV", object()))
    fake_pipeline["calls"].clear()

    at = new_app()
    at.session_state["batch_results"] = results
    at.session_state["batch_summary_path"] = pipeline.save_batch_summary(results)
    return at.run(), results


def download_labels(at):
    return [d.proto.label for d in at.get("download_button")]


def test_batch_results_are_grouped(batch):
    at, _ = batch
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["✅ Generated"] == "1" and metrics["⏸ Held for review"] == "1" and metrics["❌ Failed"] == "1"
    assert any(b.label == "✅ Generate CV & cover letter" for b in at.button)
    assert any("The file is empty" in c.value for c in at.caption)
    # Only the generated role has documents to download
    assert download_labels(at) == ["⬇ Download CV", "⬇ Download ATS CV", "⬇ Download Cover Letter"]


def test_approving_a_held_role_generates_its_documents(batch, fake_pipeline):
    at, results = batch
    click(at, "✅ Generate CV & cover letter")

    assert not at.exception
    assert fake_pipeline["calls"] == ["tailor", "letter"]
    assert results[1]["approved"] and results[1]["documents"]
    assert {m.label: m.value for m in at.metric}["✅ Generated"] == "2"
    assert not any(b.label == "✅ Generate CV & cover letter" for b in at.button)
    assert any("approved after review" in s.value for s in at.success)
    assert len(download_labels(at)) == 6, "the approved role should now have its 3 downloads"
    summary = open(at.session_state.batch_summary_path, encoding="utf-8").read()
    assert "HELD FOR REVIEW (0)" in summary and "approved after review" in summary


def test_failed_approval_keeps_the_role_held(batch, fake_pipeline):
    at, results = batch
    fake_pipeline["fail_on"] = "tailor"
    click(at, "✅ Generate CV & cover letter")

    assert pipeline.is_held(results[1])
    assert any("Generating documents failed" in e.value and "tailor exploded" in e.value for e in at.error)
    assert any(b.label == "✅ Generate CV & cover letter" for b in at.button)


def test_clear_batch_results(batch):
    at, _ = batch
    click(at, "🧹 Clear batch results")
    assert at.session_state.batch_results == []
    assert not any(m.label == "⏸ Held for review" for m in at.metric)
