"""The two gates: stress test and keyword match."""
import os

import pytest

import keyword_match
import stress_test


# --- Stress test ------------------------------------------------------------------

def test_run_stress_test(fake_client):
    client = fake_client('{"overall": "pass", "verdict": "Good fit.", "parameters": ['
                         '{"name": "Location", "result": "PASS", "reason": "Copenhagen"},'
                         '{"name": "Salary", "result": "flag", "reason": "Not stated"}]}')
    report = stress_test.run_stress_test("JD TEXT", client)
    assert report["overall"] == "PASS"
    assert [p["result"] for p in report["parameters"]] == ["PASS", "FLAG"]
    assert "JD TEXT" in client.prompts[0]


def test_stress_report_unknown_overall_needs_a_human():
    """An unrecognised verdict must never be treated as a PASS."""
    assert stress_test.normalise_stress_report({"overall": "probably fine"})["overall"] == "BORDERLINE"
    assert stress_test.normalise_stress_report({})["overall"] == "BORDERLINE"


def test_stress_report_cleans_parameters():
    report = stress_test.normalise_stress_report({
        "overall": "FAIL",
        "parameters": [{"result": "weird"}, "not a dict", {"name": "Permit", "result": "fail", "reason": None}],
    })
    assert report["parameters"] == [
        {"name": "Unnamed check", "result": "FLAG", "reason": ""},
        {"name": "Permit", "result": "FAIL", "reason": ""},
    ]
    assert report["verdict"]


def test_stress_report_survives_parameters_not_being_a_list():
    assert stress_test.normalise_stress_report({"overall": "PASS", "parameters": "oops"})["parameters"] == []


# --- Keyword match ----------------------------------------------------------------

def test_run_keyword_match(fake_client):
    client = fake_client('{"score": 8, "matching_keywords": ["Agile"], "missing_keywords": ["SAFe"], '
                         '"gaps": "No SAFe.", "recommendation": "Send as is"}')
    report = keyword_match.run_keyword_match("JD TEXT", "CV TEXT", client)
    assert report["score"] == 8
    assert report["missing_keywords"] == ["SAFe"]
    assert "JD TEXT" in client.prompts[0] and "CV TEXT" in client.prompts[0]


@pytest.mark.parametrize("score, expected", [
    (7, 7), ("7", 7), ("7/10", 7), (6.6, 7), (14, 10), (-2, 0),
])
def test_keyword_score_is_coerced(score, expected):
    assert keyword_match.normalise_keyword_report({"score": score})["score"] == expected


@pytest.mark.parametrize("score", [None, "high", "", [7]])
def test_keyword_score_must_be_usable(score):
    with pytest.raises(ValueError, match="no usable score"):
        keyword_match.normalise_keyword_report({"score": score})


def test_keyword_lists_are_cleaned():
    report = keyword_match.normalise_keyword_report({
        "score": 5, "matching_keywords": "Scrum", "missing_keywords": ["SAFe", "", None, "  "],
    })
    assert report["matching_keywords"] == ["Scrum"]
    assert report["missing_keywords"] == ["SAFe"]
    assert report["gaps"] == "" and report["recommendation"] == ""


def test_save_keyword_report_writes_utf8(tmp_path):
    report = keyword_match.normalise_keyword_report({
        "score": 6, "matching_keywords": ["Kanban → flow"], "missing_keywords": ["Ørsted domain"],
        "gaps": "Needs ≥5 yrs", "recommendation": "tweak",
    })
    keyword_match.save_keyword_report(report, str(tmp_path))
    text = (tmp_path / "keyword_match_report.txt").read_text(encoding="utf-8")
    assert "Kanban → flow" in text and "Ørsted domain" in text and "≥5" in text
