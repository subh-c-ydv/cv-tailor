import json

import pytest

import tailor_cv
from conftest import SYNTHETIC_COMPETENCIES, node_available


@pytest.fixture
def structure():
    return tailor_cv.load_cv_structure()


# --- cv_structure.txt ------------------------------------------------------------

def test_load_cv_structure(structure):
    assert structure["section_map"]["NAME"] == "header"
    assert "PROFESSIONAL SUMMARY" in structure["narrative_sections"]
    assert "PROFESSIONAL EXPERIENCE" in structure["narrative_sections"]
    assert structure["section_map"]["CORE COMPETENCIES"] == "core_competencies"
    assert structure["section_map"]["RECOGNITION & PROFESSIONAL COMMUNITY"] == "recognition_and_professional_community"


# --- Extraction ---------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    (" | Leading pipe", "Leading pipe"),
    ("Trailing pipe | ", "Trailing pipe"),
    ("Too    many   spaces", "Too many spaces"),
    ("", ""),
])
def test_normalize_text(raw, expected):
    assert tailor_cv.normalize_text(raw) == expected


def test_extract_cv_sections(synthetic_cv, structure):
    sections = tailor_cv.extract_cv_sections(synthetic_cv, structure)
    assert sections["header"][0] == "Jane Example"
    assert sections["header"][1] == "Delivery Leadership | Programme Governance"  # tab -> " | "
    assert sections["professional_summary"] == ["Delivery leader with fifteen years of experience."]
    assert sections["professional_experience"][0].startswith("Delivery Manager | Example Co")
    assert sections["tables"]["core_competencies"] == SYNTHETIC_COMPETENCIES
    assert sections["tables"]["languages"] == [["English", "Fluent"]]


def test_extract_cv_sections_without_header_fails_clearly(tmp_path, structure):
    from docx import Document
    doc = Document()
    doc.add_paragraph("NAME")  # a heading only, no content before sections
    path = str(tmp_path / "empty.docx")
    doc.save(path)
    with pytest.raises(ValueError, match="No header lines"):
        tailor_cv.extract_cv_sections(path, structure)


# --- Validating the tailoring reply -------------------------------------------------

def test_normalise_tailored_full_reply():
    result = tailor_cv.normalise_tailored({
        "tagline": " A │ B ",
        "professional_summary": "Summary.",
        "professional_experience": ["Line 1", "", "Line 2"],
        "core_competencies": [["Label", "Desc"], ["Only label"], [], "junk", ["", "no label"]],
    })
    assert result == {
        "tagline": "A │ B",
        "professional_summary": "Summary.",
        "professional_experience": ["Line 1", "Line 2"],
        "core_competencies": [["Label", "Desc"], ["Only label", ""]],
    }


def test_normalise_tailored_accepts_experience_as_text():
    result = tailor_cv.normalise_tailored({
        "professional_summary": ["Part one.", "Part two."],
        "professional_experience": "Line 1\nLine 2",
    })
    assert result["professional_summary"] == "Part one. Part two."
    assert result["professional_experience"] == ["Line 1", "Line 2"]
    assert result["tagline"] == "" and result["core_competencies"] == []


@pytest.mark.parametrize("raw, missing", [
    ({"professional_experience": ["x"]}, "professional_summary"),
    ({"professional_summary": "x"}, "professional_experience"),
    ({"professional_summary": "x", "professional_experience": []}, "professional_experience"),
])
def test_normalise_tailored_requires_summary_and_experience(raw, missing):
    with pytest.raises(ValueError, match=missing):
        tailor_cv.normalise_tailored(raw)


def test_tailor_with_claude_sends_cv_and_gaps(fake_client, synthetic_cv, structure):
    sections = tailor_cv.extract_cv_sections(synthetic_cv, structure)
    client = fake_client(json.dumps({
        "tagline": "Programme Governance │ Delivery Leadership",
        "professional_summary": "Tailored.",
        "core_competencies": [["Agile Coaching", "Coaches teams"]],
        "professional_experience": ["Delivery Manager | Example Co | 2020 – 2024"],
    }))
    result = tailor_cv.tailor_with_claude(sections, "THE JD", client, structure,
                                          missing_keywords=["SAFe", "OKRs"], gaps="No SAFe")
    prompt = client.prompts[0]
    for expected in ("THE JD", "Delivery Leadership | Programme Governance",
                     "1. Delivery Leadership — Leads cross-team delivery",
                     "Cut release cycle time by 30%", "SAFe, OKRs", "No SAFe"):
        assert expected in prompt
    assert "{" not in prompt.split("Return your response as JSON")[0], "unfilled placeholder in prompt"
    assert result["professional_summary"] == "Tailored."
    assert client.calls[0]["max_tokens"] >= 8000


# --- Building the Word documents (runs the real Node.js builders) -------------------

needs_node = pytest.mark.skipif(not node_available(), reason="Node.js or node_modules/docx not installed")


def _docx_paragraphs(path):
    from docx import Document
    return [p.text for p in Document(path).paragraphs]


def _docx_table_text(path):
    from docx import Document
    return [[c.text for c in r.cells] for t in Document(path).tables for r in t.rows]


@needs_node
def test_build_cv_documents_uses_tailored_content(synthetic_cv, structure, tmp_path):
    sections = tailor_cv.extract_cv_sections(synthetic_cv, structure)
    tailored = tailor_cv.normalise_tailored({
        "tagline": "Programme Governance  │  Delivery Leadership",
        "professional_summary": "Tailored summary.",
        "core_competencies": [["Agile Coaching", "Coaches teams"]],
        "professional_experience": [
            "Delivery Manager | Example Co · Copenhagen | 2020 – 2024",
            "• Cut release cycle time by 30%",
            "• --",
            "Earlier Career (2002 – 2014)",
            "Various Organisations | 2002 – 2014",
            "• Built foundations",
        ],
    })
    out = tmp_path / "out"
    out.mkdir()

    paths = tailor_cv.build_cv_documents(sections, structure, tailored, "Lead: Data/AI?", "Acme", str(out))

    assert paths["filename_base"] == "Subhash_Yadav_Lead-_Data-AI-_Acme"
    styled = _docx_paragraphs(paths["cv_path"])

    # Header: name kept, tagline replaced, contact line kept
    assert styled[0] == "Jane Example"
    assert styled[1] == "Programme Governance │ Delivery Leadership"
    assert "jane@example.com" in styled[2]

    # Tailored competencies replace the master pool; untouched tables are kept
    tables = _docx_table_text(paths["cv_path"])
    assert ["Agile Coaching", "Coaches teams"] in tables
    assert ["Delivery Leadership", "Leads cross-team delivery"] not in tables
    assert ["English", "Fluent"] in tables

    # Experience parsing in build_docx.js
    assert "Tailored summary." in styled
    assert "Delivery Manager" in styled
    assert "Example Co · Copenhagen   2020 – 2024" in styled
    assert "• Cut release cycle time by 30%" in styled
    assert "Earlier Career (2002 – 2014)" in styled
    assert "Various Organisations   2002 – 2014" in styled
    assert not any(p.strip() in ("• --", "--") for p in styled), "placeholder bullet was rendered"

    # ATS version: no tables, competencies flattened to names
    assert _docx_table_text(paths["cv_ats_path"]) == []
    ats = _docx_paragraphs(paths["cv_ats_path"])
    assert "Agile Coaching" in ats
    assert "Programme Governance │ Delivery Leadership" in ats


def _bold_runs(path):
    from docx import Document
    return [r.text for p in Document(path).paragraphs for r in p.runs if r.bold]


@needs_node
def test_markdown_bold_is_rendered_not_printed(synthetic_cv, structure, tmp_path):
    """Claude marks key metrics with **bold**; the builders must render it as
    real bold, never print the asterisks (bug in every CV from v1.6 to v1.8)."""
    import fact_check
    sections = tailor_cv.extract_cv_sections(synthetic_cv, structure)
    tailored = tailor_cv.normalise_tailored({
        "professional_summary": "Lifted NPS from **-5 to +35** and cut costs by **12%**.",
        "professional_experience": [
            "Delivery Manager | Example Co | 2020 – 2024",
            "• Reduced cycle time to **below 14 days** within two quarters",
            "• A stray ** marker should vanish",
        ],
    })
    paths = tailor_cv.build_cv_documents(sections, structure, tailored, "PM", "Acme", str(tmp_path))

    for path in (paths["cv_path"], paths["cv_ats_path"]):
        text = "\n".join(_docx_paragraphs(path))
        assert "**" not in text
        assert "Lifted NPS from -5 to +35 and cut costs by 12%." in text
        assert "• Reduced cycle time to below 14 days within two quarters" in text
        assert "• A stray  marker should vanish" in text
        bold = _bold_runs(path)
        for metric in ("-5 to +35", "12%", "below 14 days"):
            assert metric in bold, f"{metric!r} not bold in {path}"
        assert "Lifted NPS from " not in bold and " within two quarters" not in bold
        assert not [f for f in fact_check.check_docx(path, []) if f.rule == "markdown_leftover"]


@needs_node
def test_build_cv_documents_falls_back_to_master_content(synthetic_cv, structure, tmp_path):
    sections = tailor_cv.extract_cv_sections(synthetic_cv, structure)
    tailored = tailor_cv.normalise_tailored({
        "professional_summary": "S.", "professional_experience": ["• One"],
    })
    paths = tailor_cv.build_cv_documents(sections, structure, tailored, "PM", "Acme", str(tmp_path))
    assert _docx_paragraphs(paths["cv_path"])[1] == "Delivery Leadership | Programme Governance"
    assert ["Portfolio Governance", "Runs portfolio reviews"] in _docx_table_text(paths["cv_path"])
