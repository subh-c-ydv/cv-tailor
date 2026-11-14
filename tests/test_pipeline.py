"""pipeline.py: gate rules, the shared steps, and batch processing."""
import os

import pytest

import pipeline
from conftest import PASS_REPORT, keyword_report
from pipeline import BORDERLINE, FAIL, PASS


def stress(overall, verdict="v"):
    return {"overall": overall, "verdict": verdict, "parameters": []}


# --- Gate rules ---------------------------------------------------------------------

@pytest.mark.parametrize("overall, score, expected", [
    ("PASS", 10, PASS),
    ("PASS", 7, PASS),
    ("PASS", 6, BORDERLINE),
    ("PASS", 4, BORDERLINE),
    ("PASS", 3, FAIL),
    ("PASS", 0, FAIL),
    ("BORDERLINE", 9, BORDERLINE),
    ("BORDERLINE", 5, BORDERLINE),
    ("BORDERLINE", 2, FAIL),
    ("FAIL", 10, FAIL),
    ("FAIL", None, FAIL),
])
def test_assess(overall, score, expected):
    keywords = keyword_report(score) if score is not None else None
    assert pipeline.assess(stress(overall), keywords)[0] == expected


def test_assess_gives_every_reason():
    status, reasons = pipeline.assess(stress("BORDERLINE", "Salary unclear."), keyword_report(5))
    assert status == BORDERLINE
    assert reasons == ["Borderline stress test — Salary unclear.", "Moderate keyword match (5/10)"]
    assert pipeline.assess(stress("PASS"), keyword_report(9)) == (PASS, [])


@pytest.mark.parametrize("score, band", [(0, "low"), (3, "low"), (4, "moderate"), (6, "moderate"), (7, "strong")])
def test_keyword_band(score, band):
    assert pipeline.keyword_band(score) == band


# --- Steps ----------------------------------------------------------------------------

def test_run_checks_skips_keyword_match_after_a_stress_fail(fake_pipeline):
    fake_pipeline["stress"] = stress("FAIL", "No permit.")
    checks = pipeline.run_checks("JD", "CV", object())
    assert fake_pipeline["calls"] == ["stress"]
    assert checks["status"] == FAIL and checks["keyword_report"] is None


def test_make_documents(fake_pipeline, isolate):
    details = {"job_title": "Delivery Lead", "company_name": "Acme", "seniority_tier": "mid",
               "problem_specificity": "generic", "agency_posted": True}
    docs = pipeline.make_documents("JD", "CV", details, object(), keyword_report(8))

    assert docs["output_dir"] == str(isolate / "Delivery Lead @ Acme")
    assert os.path.exists(os.path.join(docs["output_dir"], "keyword_match_report.txt"))
    assert os.path.exists(docs["cv"]["cv_path"]) and os.path.exists(docs["letter"]["path"])
    assert fake_pipeline["tailor_inputs"] == (["SAFe"], "No SAFe.")
    # agency-posted roles use the agency row of cover_letter_weights.txt
    assert docs["letter"]["shape"] in ("direct_short", "three_strengths")


def test_forced_letter_shape(fake_pipeline, tmp_path):
    details = {"job_title": "PM", "company_name": "Acme"}
    letter = pipeline.make_cover_letter("JD", "CV", details, str(tmp_path), object(), shape="question_led")
    assert letter["shape"] == "question_led" and letter["shape_reason"] == "chosen manually"
    assert os.path.exists(letter["path"])


# --- Batch ----------------------------------------------------------------------------

def test_batch_pass_generates_documents(fake_pipeline):
    result = pipeline.process_batch_item("a.txt", b"A JD", "CV", object())
    assert result["status"] == PASS
    assert result["documents"]["cv"]["cv_path"]
    assert fake_pipeline["calls"] == ["stress", "keyword", "details", "tailor", "letter"]


@pytest.mark.parametrize("overall, score", [("BORDERLINE", 9), ("PASS", 5), ("BORDERLINE", 5)])
def test_batch_borderline_is_held_without_documents(fake_pipeline, isolate, overall, score):
    fake_pipeline["stress"] = stress(overall)
    fake_pipeline["keyword_score"] = score
    result = pipeline.process_batch_item("b.txt", b"A JD", "CV", object())

    assert result["status"] == BORDERLINE and pipeline.is_held(result)
    assert result["documents"] is None
    assert result["job_details"]["job_title"] == "Delivery Lead"  # shown while you review
    assert "tailor" not in fake_pipeline["calls"] and "letter" not in fake_pipeline["calls"]
    assert not os.listdir(isolate), "no output folder until the role is approved"


def test_approving_a_held_role_reuses_the_checks(fake_pipeline):
    fake_pipeline["keyword_score"] = 5
    result = pipeline.process_batch_item("b.txt", b"A JD", "CV", object())
    fake_pipeline["calls"].clear()

    pipeline.approve_held_role(result, "CV", object(), shape="story_first")

    assert fake_pipeline["calls"] == ["tailor", "letter"], "checks and role details must not be paid for twice"
    assert result["approved"] and not pipeline.is_held(result)
    assert result["documents"]["letter"]["shape"] == "story_first"
    assert fake_pipeline["tailor_inputs"] == (["SAFe"], "No SAFe.")


def test_only_held_roles_can_be_approved(fake_pipeline):
    result = pipeline.process_batch_item("a.txt", b"A JD", "CV", object())
    with pytest.raises(ValueError, match="not waiting for review"):
        pipeline.approve_held_role(result, "CV", object())


@pytest.mark.parametrize("data, fail_on, expected", [
    (b"   ", None, "The file is empty"),
    (b"A JD", "stress", "stress exploded"),
    (b"A JD", "tailor", "tailor exploded"),
])
def test_batch_errors_become_fails(fake_pipeline, data, fail_on, expected):
    fake_pipeline["fail_on"] = fail_on
    result = pipeline.process_batch_item("x.txt", data, "CV", object())
    assert result["status"] == FAIL
    assert expected in result["error"]
    assert any(expected in r for r in result["reasons"])


def test_batch_low_keyword_score_fails(fake_pipeline):
    fake_pipeline["keyword_score"] = 2
    result = pipeline.process_batch_item("x.txt", b"A JD", "CV", object())
    assert result["status"] == FAIL and "details" not in fake_pipeline["calls"]


def test_batch_decodes_cp1252_uploads(fake_pipeline):
    seen = []
    fake_pipeline["stress"] = lambda jd: seen.append(jd) or PASS_REPORT
    pipeline.process_batch_item("x.txt", "Konsulent – København".encode("cp1252"), "CV", object())
    assert seen == ["Konsulent – København"]


def test_batch_summary(fake_pipeline, isolate):
    passed = pipeline.process_batch_item("a.txt", b"JD", "CV", object())
    fake_pipeline["keyword_score"] = 5
    held = pipeline.process_batch_item("b.txt", b"JD", "CV", object())
    failed = pipeline.process_batch_item("c.txt", b"  ", "CV", object())

    path = pipeline.save_batch_summary([passed, held, failed])
    text = open(path, encoding="utf-8").read()
    assert "GENERATED (1)" in text and "HELD FOR REVIEW (1)" in text and "FAILED (1)" in text
    assert "Delivery Lead @ Acme  (keyword: 8/10)  [letter:" in text
    assert "Moderate keyword match (5/10)" in text and "File: b.txt" in text
    assert "c.txt" in text and "The file is empty" in text

    # Approving rewrites the same file
    pipeline.approve_held_role(held, "CV", object())
    assert pipeline.save_batch_summary([passed, held, failed], path) == path
    text = open(path, encoding="utf-8").read()
    assert "GENERATED (2)" in text and "HELD FOR REVIEW (0)" in text and "approved after review" in text
