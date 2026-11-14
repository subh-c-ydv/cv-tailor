"""The CV Tailor pipeline, shared by the Single JD and Batch tabs.

Steps, in order:
  1. Checks  - stress test, then keyword match (the two gates)
  2. Role    - job title, company, and the classification used to pick a
               cover letter shape
  3. CV      - tailor, then build the styled and ATS .docx
  4. Letter  - pick a shape, write the letter, build the .docx

assess() is the one place the gate rules live. The Single JD tab runs the
steps one at a time so it can ask you at each gate; the Batch tab runs them
all, and holds borderline roles back until you approve them.

Steps are called through their modules (stress_test.run_stress_test rather
than an imported name) so tests can replace any one of them.
"""
import os
from datetime import datetime

import config
import generate_cover_letter
import keyword_match
import shape_selector
import stress_test
import tailor_cv
import utils

PASS = "PASS"
BORDERLINE = "BORDERLINE"
FAIL = "FAIL"

# Keyword match score thresholds (0-10)
KEYWORD_FAIL_MAX = 3     # at or below: the role fails
KEYWORD_REVIEW_MAX = 6   # at or below: borderline, needs your review


# ---------------------------------------------------------------------------
# Gate rules
# ---------------------------------------------------------------------------

def keyword_band(score):
    if score <= KEYWORD_FAIL_MAX:
        return "low"
    if score <= KEYWORD_REVIEW_MAX:
        return "moderate"
    return "strong"


def assess(stress_report, keyword_report=None):
    """Apply the gate rules and return (status, reasons).

      FAIL       stress test FAIL, or keyword score of 3 or below
      BORDERLINE stress test BORDERLINE and/or keyword score of 4-6
      PASS       everything else

    keyword_report is None when the keyword match wasn't run, which only
    happens after a stress test FAIL."""
    if stress_report["overall"] == FAIL:
        return FAIL, [f"Failed stress test — {stress_report['verdict']}"]

    status, reasons = PASS, []
    if stress_report["overall"] == BORDERLINE:
        status = BORDERLINE
        reasons.append(f"Borderline stress test — {stress_report['verdict']}")

    if keyword_report is not None:
        score = keyword_report["score"]
        if score <= KEYWORD_FAIL_MAX:
            return FAIL, reasons + [f"Keyword match too low ({score}/10)"]
        if score <= KEYWORD_REVIEW_MAX:
            status = BORDERLINE
            reasons.append(f"Moderate keyword match ({score}/10)")

    return status, reasons


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def run_checks(jd_text, cv_text, client):
    """Both gates. The keyword match is skipped after a stress test FAIL,
    since the role is out either way."""
    stress_report = stress_test.run_stress_test(jd_text, client)
    keyword_report = None
    if stress_report["overall"] != FAIL:
        keyword_report = keyword_match.run_keyword_match(jd_text, cv_text, client)
    status, reasons = assess(stress_report, keyword_report)
    return {
        "status": status,
        "reasons": reasons,
        "stress_report": stress_report,
        "keyword_report": keyword_report,
    }


def identify_role(jd_text, client):
    return utils.extract_job_details(jd_text, client)


def start_application(job_details, keyword_report=None):
    """Create the output folder and save the keyword report into it."""
    output_dir = utils.make_output_dir(job_details["job_title"], job_details["company_name"])
    if keyword_report:
        keyword_match.save_keyword_report(keyword_report, output_dir)
    return output_dir


def _gap_guidance(keyword_report):
    if not keyword_report:
        return [], ""
    return keyword_report["missing_keywords"], keyword_report["gaps"]


def make_cv(jd_text, job_details, output_dir, client, keyword_report=None):
    """Tailor the master CV to this JD and build both .docx versions.
    Returns {"filename_base", "cv_path", "cv_ats_path"}."""
    missing_keywords, gaps = _gap_guidance(keyword_report)
    structure = tailor_cv.load_cv_structure()
    sections = tailor_cv.extract_cv_sections(config.CV_PATH, structure)
    tailored = tailor_cv.tailor_with_claude(
        sections, jd_text, client, structure,
        missing_keywords=missing_keywords, gaps=gaps,
    )
    return tailor_cv.build_cv_documents(
        sections, structure, tailored,
        job_details["job_title"], job_details["company_name"], output_dir,
    )


def choose_letter_shape(job_details, shape=None):
    """A shape forced from the sidebar, or one chosen from the role."""
    if shape:
        return shape, "chosen manually"
    return shape_selector.select_shape(job_details)


def make_cover_letter(jd_text, cv_text, job_details, output_dir, client,
                      keyword_report=None, shape=None):
    """Write the cover letter and build its .docx.
    Returns {"text", "shape", "shape_reason", "path", "filename"}."""
    title, company = job_details["job_title"], job_details["company_name"]
    missing_keywords, gaps = _gap_guidance(keyword_report)
    shape, shape_reason = choose_letter_shape(job_details, shape)

    text = generate_cover_letter.generate_cover_letter(
        jd_text, cv_text, title, company, client,
        missing_keywords=missing_keywords, gaps=gaps, shape=shape,
    )
    filename = utils.cover_letter_filename(title, company)
    path = os.path.join(output_dir, filename)
    generate_cover_letter.build_cover_letter_docx(text, title, company, path)
    return {"text": text, "shape": shape, "shape_reason": shape_reason,
            "path": path, "filename": filename}


def make_documents(jd_text, cv_text, job_details, client, keyword_report=None, shape=None):
    """Steps 3 and 4 together: output folder, CV and cover letter."""
    output_dir = start_application(job_details, keyword_report)
    cv = make_cv(jd_text, job_details, output_dir, client, keyword_report)
    letter = make_cover_letter(jd_text, cv_text, job_details, output_dir, client,
                               keyword_report, shape)
    return {"output_dir": output_dir, "cv": cv, "letter": letter}


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------

def new_batch_result(filename):
    return {
        "filename": filename,
        "jd_text": "",
        "status": FAIL,
        "reasons": [],
        "error": None,
        "stress_report": None,
        "keyword_report": None,
        "job_details": None,
        "documents": None,
        "approved": False,
    }


def process_batch_item(filename, data, cv_text, client, shape=None):
    """Run one uploaded JD through the pipeline.

      PASS        documents are generated straight away
      BORDERLINE  held for review: checks and role details are kept, but
                  nothing is generated until approve_held_role() is called
      FAIL        stops; an unexpected error is also recorded as a FAIL so
                  one bad JD never stops the rest of the batch"""
    result = new_batch_result(filename)
    try:
        jd_text = utils.decode_text_bytes(data)
        if not jd_text.strip():
            raise ValueError("The file is empty.")
        result["jd_text"] = jd_text

        result.update(run_checks(jd_text, cv_text, client))
        if result["status"] != FAIL:
            result["job_details"] = identify_role(jd_text, client)
        if result["status"] == PASS:
            result["documents"] = make_documents(
                jd_text, cv_text, result["job_details"], client,
                result["keyword_report"], shape,
            )
    except Exception as e:
        result["status"] = FAIL
        result["error"] = str(e)
        result["reasons"] = result["reasons"] + [f"Processing error: {e}"]
    return result


def is_held(result):
    return result["status"] == BORDERLINE and not result["documents"]


def approve_held_role(result, cv_text, client, shape=None):
    """Generate documents for a borderline role you have reviewed. Reuses the
    stored checks and role details, so nothing is paid for twice."""
    if not is_held(result):
        raise ValueError(f"{result['filename']} is not waiting for review.")
    result["documents"] = make_documents(
        result["jd_text"], cv_text, result["job_details"], client,
        result["keyword_report"], shape,
    )
    result["approved"] = True
    return result


def batch_label(result):
    details = result.get("job_details")
    if details:
        return f"{details['job_title']} @ {details['company_name']}"
    return result["filename"]


def _summary_line(result):
    line = f"  {batch_label(result)}"
    if result["keyword_report"]:
        line += f"  (keyword: {result['keyword_report']['score']}/10)"
    if result["documents"]:
        line += f"  [letter: {result['documents']['letter']['shape']}]"
    if result["approved"]:
        line += "  — approved after review"
    lines = [line] + [f"      {reason}" for reason in result["reasons"]]
    if result["job_details"] and result["status"] != PASS:
        lines.append(f"      File: {result['filename']}")
    return lines


def batch_summary_lines(results, when=None):
    when = when or datetime.now()
    generated = [r for r in results if r["documents"]]
    held = [r for r in results if is_held(r)]
    failed = [r for r in results if r["status"] == FAIL]

    lines = ["BATCH SUMMARY", f"Run: {when.strftime('%d %B %Y, %H:%M')}", "=" * 40]
    for title, group in (("GENERATED", generated), ("HELD FOR REVIEW", held), ("FAILED", failed)):
        lines += ["", f"{title} ({len(group)})"]
        for r in group:
            lines += _summary_line(r)
    lines += [
        "", "-" * 40,
        f"Total: {len(results)}",
        f"Generated: {len(generated)}",
        f"Held for review: {len(held)}",
        f"Failed: {len(failed)}",
    ]
    return lines


def save_batch_summary(results, path=None):
    """Write the summary file. Pass the same path again after approving a
    held role to update it in place."""
    if path is None:
        folder = os.path.join(utils.OUTPUTS_DIR, "batch-summaries")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"batch_summary_{datetime.now():%Y_%m_%d_%H_%M_%S}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(batch_summary_lines(results)))
    return path
