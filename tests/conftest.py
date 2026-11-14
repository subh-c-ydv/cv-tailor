"""Shared fixtures. Every test runs offline: real Claude calls are blocked,
outputs go to a temporary folder, and the cover letter shape memory is
redirected so tests never touch your real cv-outputs."""
import os
import shutil
import sys
import types

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import anthropic  # noqa: E402
import config  # noqa: E402
import shape_selector  # noqa: E402
import utils  # noqa: E402

TEST_PROFILE = '''
name = "Jane Example"
contact_line = "+45 00 00 00 00  ·  jane@example.com  ·  Copenhagen"
home_base = "Testby Station"
min_salary = "12,345 DKK per month"
candidate_profile = """
- TEST PROFILE LINE: based in Testby
"""
'''


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    """Keep every test away from the network, from real output files and
    from your real personal profile."""
    profile = tmp_path / "profile.toml"
    profile.write_text(TEST_PROFILE, encoding="utf-8")
    monkeypatch.setattr(config, "PROFILE_PATH", str(profile))

    outputs = tmp_path / "cv-outputs"
    outputs.mkdir()
    monkeypatch.setattr(utils, "OUTPUTS_DIR", str(outputs))
    monkeypatch.setattr(shape_selector, "STATE_PATH", str(outputs / ".cover_letter_state.json"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-never-sent")

    def no_network(*args, **kwargs):
        raise AssertionError("A test tried to create a real Anthropic client. Use the fake_client fixture.")
    monkeypatch.setattr(anthropic, "Anthropic", no_network)
    return outputs


class FakeClient:
    """Stands in for anthropic.Anthropic. Returns queued replies in order and
    records every prompt it was sent."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []
        self.calls = []
        self.messages = types.SimpleNamespace(create=self._create)

    def queue(self, text, stop_reason="end_turn"):
        self.replies.append((text, stop_reason))
        return self

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        self.prompts.append(kwargs["messages"][0]["content"])
        if not self.replies:
            raise AssertionError("FakeClient received more calls than replies were queued.")
        reply = self.replies.pop(0)
        text, stop_reason = reply if isinstance(reply, tuple) else (reply, "end_turn")
        return types.SimpleNamespace(
            stop_reason=stop_reason,
            content=[types.SimpleNamespace(type="text", text=text)],
        )


@pytest.fixture
def fake_client():
    return FakeClient


# --- A small, made-up master CV that follows cv_structure.txt ---------------

SYNTHETIC_COMPETENCIES = [
    ["Delivery Leadership", "Leads cross-team delivery"],
    ["Portfolio Governance", "Runs portfolio reviews"],
    ["Agile Coaching", "Coaches teams"],
]


def _build_synthetic_cv(path):
    from docx import Document

    doc = Document()
    doc.add_paragraph("Jane Example")
    tagline = doc.add_paragraph()
    tagline.add_run("Delivery Leadership")
    tagline.add_run().add_tab()  # tabs become " | " during extraction
    tagline.add_run("Programme Governance")
    doc.add_paragraph("+45 0000 0000 · jane@example.com · Copenhagen")

    doc.add_paragraph("PROFESSIONAL SUMMARY")
    doc.add_paragraph("Delivery leader with fifteen years of experience.")

    doc.add_paragraph("CORE COMPETENCIES")
    table = doc.add_table(rows=0, cols=2)
    for label, desc in SYNTHETIC_COMPETENCIES:
        cells = table.add_row().cells
        cells[0].text, cells[1].text = label, desc

    doc.add_paragraph("PROFESSIONAL EXPERIENCE")
    doc.add_paragraph("Delivery Manager | Example Co · Copenhagen | 2020 – 2024")
    doc.add_paragraph("• Cut release cycle time by 30%")

    doc.add_paragraph("LANGUAGES")
    lang = doc.add_table(rows=1, cols=2)
    lang.rows[0].cells[0].text, lang.rows[0].cells[1].text = "English", "Fluent"

    doc.save(path)
    return path


@pytest.fixture
def synthetic_cv(tmp_path):
    return _build_synthetic_cv(str(tmp_path / "master_cv.docx"))


PASS_REPORT = {"overall": "PASS", "verdict": "Good fit.", "parameters": [
    {"name": "Location", "result": "PASS", "reason": "Copenhagen"}]}


def keyword_report(score):
    return {"score": score, "matching_keywords": ["Agile"], "missing_keywords": ["SAFe"],
            "gaps": "No SAFe.", "recommendation": "Send"}


@pytest.fixture
def fake_pipeline(monkeypatch):
    """Replace every paid or slow step with a fake. Returns a dict the test
    can tweak (stress report, keyword score, failures) and inspect (calls)."""
    import generate_cover_letter
    import keyword_match
    import stress_test
    import tailor_cv

    state = {"stress": PASS_REPORT, "keyword_score": 8, "calls": [], "fail_on": None}

    def step(name):
        state["calls"].append(name)
        if state["fail_on"] == name:
            raise RuntimeError(f"{name} exploded")

    monkeypatch.setattr(utils, "get_client", lambda: object())
    monkeypatch.setattr(utils, "read_cv_text", lambda: "CV TEXT")

    def fake_stress(jd, client):
        step("stress")
        return state["stress"](jd) if callable(state["stress"]) else state["stress"]
    monkeypatch.setattr(stress_test, "run_stress_test", fake_stress)

    def fake_keyword(jd, cv, client):
        step("keyword")
        return keyword_report(state["keyword_score"])
    monkeypatch.setattr(keyword_match, "run_keyword_match", fake_keyword)

    def fake_details(jd, client):
        step("details")
        return {"job_title": "Delivery Lead", "company_name": "Acme",
                "seniority_tier": "senior", "problem_specificity": "specific", "agency_posted": False}
    monkeypatch.setattr(utils, "extract_job_details", fake_details)

    monkeypatch.setattr(tailor_cv, "extract_cv_sections",
                        lambda path, structure: {"header": ["Jane", "Tagline"], "tables": {}})

    def fake_tailor(sections, jd, client, structure, missing_keywords=None, gaps=None):
        step("tailor")
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
        step("letter")
        state["letter_shape"] = shape
        return "Dear team,\n\nI'd like to apply."
    monkeypatch.setattr(generate_cover_letter, "generate_cover_letter", fake_letter)
    return state


def node_available():
    return bool(shutil.which("node")) and os.path.isdir(os.path.join(REPO_ROOT, "node_modules", "docx"))
