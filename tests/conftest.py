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
import shape_selector  # noqa: E402
import utils  # noqa: E402


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    """Keep every test away from the network and from real output files."""
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


def node_available():
    return bool(shutil.which("node")) and os.path.isdir(os.path.join(REPO_ROOT, "node_modules", "docx"))
