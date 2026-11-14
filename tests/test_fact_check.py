import pytest

import fact_check
from fact_check import REVIEW, VIOLATION


def rules(text, allowed=()):
    return {(f.rule, f.severity) for f in fact_check.check_text(text, allowed)}


# --- Violations: each sentence below breaks one fixed factual rule ------------------

@pytest.mark.parametrize("text, rule", [
    ("Worked at CIO level across the group.", "cio_level"),
    ("Engaged at CIO-level stakeholders.", "cio_level"),
    ("Work permit: employer-sponsored (transferable).", "transferable_permit"),
    ("Managed vendors including IBM.", "wrong_vendor"),
    ("Coordinated Endava teams.", "wrong_vendor"),
    ("Led the CP&S portfolio.", "portfolio_name"),
    ("Owned the Customer Products & Services roadmap.", "portfolio_name"),
    ("Seven years at APM Terminals shaped my approach.", "apmt_tenure"),
    ("At APM Terminals for 7 years, I ran delivery.", "apmt_tenure"),
    ("Held full P&L ownership for the portfolio.", "pnl_ownership"),
    ("Accountable for the P&L of the division.", "pnl_ownership"),
    ("Certified ScrumMaster (CSM).", "csm_certification"),
    ("Reduced the defect escape rate by 40%.", "defect_metric_name"),
    ("Built PowerBI dashboards.", "tool_name"),
    ("Migrated boards to ADO.", "tool_name"),
    ("Dear {company_name} team,", "template_leftover"),
    ("I admire [Company Name]'s mission.", "template_leftover"),
    ("Cut cycle time to **below 14 days**.", "markdown_leftover"),
    ("Bunker cycle time fell from above 20 days to below 10 days.", "bunker_cycle_time"),
    ("Bunker cycle time fell to below 14 days within one quarter.", "bunker_cycle_time"),
    ("Kind regards,\nJane\n\nKind regards,", "duplicate_sign_off"),
])
def test_violations_are_caught(text, rule):
    assert (rule, VIOLATION) in rules(text)


@pytest.mark.parametrize("text, rule", [
    ("I led the payments digitalisation programme.", "led_payments"),
    ("We built a new program for onboarding.", "us_spelling"),
    ("Had four direct reports in Copenhagen.", "line_management"),
    ("Engaged vendors on-site in Serbia.", "serbia_context"),
    ("Gave full visibility of the P&L.", "pnl_mention"),
])
def test_review_items_are_flagged(text, rule):
    assert (rule, REVIEW) in rules(text)


# --- Compliant text must stay quiet (each case is a false positive we've seen or expect)

@pytest.mark.parametrize("text", [
    "Engaged stakeholders at CIO-1 level.",
    "Work permit: employer-sponsored.",
    "Managed vendors including TCS and Ubique Systems.",
    "Led the Digital Products Portfolio (DPP).",
    "Three years at APM Terminals (2022-2025).",
    "Provided trusted stewardship and full visibility of spend.",
    "Facilitated delivery of payments digitalisation.",
    "Also supported a compliance-led payment-platform integration.",  # 'led' inside a compound
    "Ran a programme of change; strong programming background.",
    "• People leader for a team of 30 — 4 direct reports each managing teams of 5–7.",  # Infosys bullet
    "At Infosys I had line management of a team of 30.",
    "Received the 2019 Maersk Star Award for work in Serbia.",
    "Bunker cycle time reduced from above 20 days to below 14 days within two quarters.",
    "Built Power BI reporting on Azure DevOps data.",
    "Kind regards,\nJane Example",
    "Improved NPS from -5 to +35 within six months.",
])
def test_compliant_text_is_clean(text):
    assert fact_check.check_text(text) == []


def test_job_title_from_the_jd_is_allowed():
    text = "I'm applying for the Program Manager role at Twoday."
    assert ("us_spelling", REVIEW) in rules(text)
    assert rules(text, allowed=["Program Manager", "Twoday"]) == set()


def test_markdown_markers_reported_once_with_count():
    findings = [f for f in fact_check.check_text("**a** and **b**") if f.rule == "markdown_leftover"]
    assert len(findings) == 1 and "4 markdown" in findings[0].message


def test_violations_sorted_before_reviews():
    findings = fact_check.check_text("A new program. Worked at CIO level.")
    assert [f.severity for f in findings] == [VIOLATION, REVIEW]


# --- Documents and the command line ------------------------------------------------

def _docx(path, paragraphs, table_rows=()):
    from docx import Document
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    if table_rows:
        table = doc.add_table(rows=0, cols=len(table_rows[0]))
        for row in table_rows:
            cells = table.add_row().cells
            for cell, value in zip(cells, row):
                cell.text = value
    doc.save(path)
    return str(path)


def test_check_docx_reads_paragraphs_and_tables(tmp_path):
    path = _docx(tmp_path / "cv.docx", ["Clean paragraph."], [["Certifications", "CSM (lapsed)"]])
    assert {f.rule for f in fact_check.check_docx(path)} == {"csm_certification"}


def test_allowed_phrases_come_from_the_output_folder_name(tmp_path):
    folder = tmp_path / "Program Manager @ Twoday"
    folder.mkdir()
    path = _docx(folder / "letter.docx", ["Applying for the Program Manager role at Twoday."])
    assert fact_check.check_docx(path) == []


def test_cli_exit_code(tmp_path, capsys):
    clean = _docx(tmp_path / "clean.docx", ["All good."])
    dirty = _docx(tmp_path / "dirty.docx", ["Worked at CIO level."])
    assert fact_check.main([clean]) == 0
    assert fact_check.main([str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "cio_level" in out and "Checked 2 document(s)" in out
    assert dirty in out
