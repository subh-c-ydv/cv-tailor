import streamlit as st
import os
import time
from datetime import datetime
from config import OUTPUTS_DIR, CV_PATH
from utils import (
    read_cv_text,
    extract_job_details,
    get_client,
    decode_text_bytes,
    make_output_dir,
    cover_letter_filename,
)
from stress_test import run_stress_test
from keyword_match import run_keyword_match, save_keyword_report
from tailor_cv import extract_cv_sections, tailor_with_claude, load_cv_structure, build_cv_documents
from generate_cover_letter import generate_cover_letter, build_cover_letter_docx
from shape_selector import select_shape, list_shapes

# --- Page config ---
st.set_page_config(
    page_title="CV Tailor",
    page_icon="📄",
    layout="wide"
)

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


# --- Helpers ---
def safe_read_bytes(path, retries=5, delay=0.4):
    """Read a file's bytes, retrying briefly if OneDrive (or any sync
    client) still has a lock on a just-written file. Raises the final
    PermissionError if it never clears."""
    for attempt in range(retries):
        try:
            with open(path, "rb") as f:
                return f.read()
        except PermissionError:
            if attempt == retries - 1:
                raise
            time.sleep(delay)


def download_button(label, path, file_name, key):
    """Show a download button for a generated file. Never crashes the page:
    a missing file shows nothing, and a locked file shows where it is saved.
    on_click="ignore" stops the click from rerunning the app, which would
    otherwise wipe batch results off the screen."""
    if not path or not os.path.exists(path):
        return
    try:
        data = safe_read_bytes(path)
    except OSError as e:
        st.warning(f"Couldn't read {file_name} for download ({e}). It is saved at: {path}")
        return
    st.download_button(
        label=label,
        data=data,
        file_name=file_name,
        mime=DOCX_MIME,
        key=key,
        on_click="ignore",
    )


def reset_session():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()


def show_step_error(step, error):
    """Explain a failed step and let the user retry it or start over, instead
    of showing a raw traceback. Retrying works because each stage only stores
    its results once the whole step has succeeded."""
    st.error(f"**{step} failed:** {error}")
    with st.expander("Technical details"):
        st.exception(error)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔁 Try again", type="primary", key="retry_failed_step"):
            st.rerun()
    with col2:
        if st.button("🔄 Start over", key="restart_after_error"):
            reset_session()


def format_shape_name(name):
    """'problem_first' -> 'Problem first' (for display only)."""
    return name.replace("_", " ").capitalize()


def stress_test_color(result):
    if result == "PASS":
        return "✅"
    elif result == "FAIL":
        return "❌"
    return "⚠️"


def render_stress_report(report):
    overall = report["overall"]
    if overall == "PASS":
        st.success(f"✅ OVERALL: PASS — {report['verdict']}")
    elif overall == "FAIL":
        st.error(f"❌ OVERALL: FAIL — {report['verdict']}")
    else:
        st.warning(f"⚠️ OVERALL: BORDERLINE — {report['verdict']}")
    st.markdown("---")
    for param in report["parameters"]:
        icon = stress_test_color(param["result"])
        st.markdown(f"{icon} **{param['name']}**: {param['reason']}")


def render_keyword_report(report):
    score = report["score"]
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Match Score", f"{score}/10")
    with col2:
        st.metric("Matching Keywords", len(report["matching_keywords"]))
    with col3:
        st.metric("Missing Keywords", len(report["missing_keywords"]))
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Matching keywords**")
        for kw in report["matching_keywords"]:
            st.markdown(f"✅ {kw}")
    with col2:
        st.markdown("**Missing keywords**")
        for kw in report["missing_keywords"]:
            st.markdown(f"❌ {kw}")
    st.markdown(f"**Gaps:** {report['gaps']}")
    st.markdown(f"**Recommendation:** {report['recommendation']}")


def render_earlier_reports():
    if st.session_state.stress_report:
        st.subheader("Stress Test Report")
        render_stress_report(st.session_state.stress_report)
        st.markdown("---")

    if st.session_state.keyword_report:
        st.subheader("Keyword Match Report")
        render_keyword_report(st.session_state.keyword_report)
        st.markdown("---")


def render_cv_downloads(key_suffix):
    st.subheader("Tailored CV")
    st.success(f"✅ CV generated — {st.session_state.job_title} at {st.session_state.company_name}")
    download_button(
        "⬇ Download Tailored CV",
        st.session_state.cv_path,
        f"{st.session_state.filename_base}.docx",
        key=f"cv_download_{key_suffix}",
    )
    download_button(
        "⬇ Download ATS-friendly CV",
        st.session_state.get("cv_ats_path"),
        f"{st.session_state.filename_base}_ATS.docx",
        key=f"cv_ats_download_{key_suffix}",
    )


def new_batch_result():
    return {
        "status": "PASS",
        "stop_reason": None,
        "job_title": "Unknown",
        "company_name": "Unknown",
        "keyword_score": None,
        "stress_report": None,
        "keyword_report": None,
        "cv_path": None,
        "cv_ats_path": None,
        "cl_path": None,
        "cv_filename": None,
        "cv_ats_filename": None,
        "cl_filename": None,
        "cl_shape": None,
        "cl_shape_reason": None,
        "output_dir": None,
    }


def process_single_jd_ui(jd_text, client, cv_text, shape_override=None):
    """Process a single JD through the full pipeline for batch mode.
    Borderline results continue to document generation — no interactive prompts.
    Only hard FAILs stop processing.

    shape_override: force a specific cover letter shape for this JD. If None,
    the shape is chosen automatically from the role's classification.
    """
    result = new_batch_result()

    # Gate 1 — Stress Test
    stress_report = run_stress_test(jd_text, client)
    result["stress_report"] = stress_report
    overall = stress_report["overall"]

    if overall == "FAIL":
        result["status"] = "FAIL"
        result["stop_reason"] = f"Failed stress test — {stress_report['verdict']}"
        return result

    if overall == "BORDERLINE":
        result["status"] = "BORDERLINE"
        result["stop_reason"] = f"Borderline stress test — {stress_report['verdict']}"
        # Continue to generate documents despite borderline

    # Gate 2 — Keyword Match
    keyword_report = run_keyword_match(jd_text, cv_text, client)
    result["keyword_report"] = keyword_report
    score = keyword_report["score"]
    result["keyword_score"] = score
    missing_keywords = keyword_report["missing_keywords"]
    gaps = keyword_report["gaps"]

    if score <= 3:
        result["status"] = "FAIL"
        result["stop_reason"] = f"Keyword match too low ({score}/10)"
        return result

    if score <= 6 and result["status"] != "BORDERLINE":
        result["status"] = "BORDERLINE"
        result["stop_reason"] = f"Moderate keyword match ({score}/10)"
        # Continue to generate documents despite borderline

    # Extract job details (title, company and the role classification)
    job_details = extract_job_details(jd_text, client)
    job_title = job_details["job_title"]
    company_name = job_details["company_name"]
    result["job_title"] = job_title
    result["company_name"] = company_name

    output_dir = make_output_dir(job_title, company_name)
    result["output_dir"] = output_dir

    save_keyword_report(keyword_report, output_dir)

    # Build CV
    structure = load_cv_structure()
    sections = extract_cv_sections(CV_PATH, structure)
    tailored = tailor_with_claude(
        sections, jd_text, client, structure,
        missing_keywords=missing_keywords,
        gaps=gaps
    )
    paths = build_cv_documents(sections, structure, tailored, job_title, company_name, output_dir)

    result["cv_path"] = paths["cv_path"]
    result["cv_filename"] = os.path.basename(paths["cv_path"])
    result["cv_ats_path"] = paths["cv_ats_path"]
    result["cv_ats_filename"] = os.path.basename(paths["cv_ats_path"])

    # Choose the cover letter shape (forced, or automatic from the classification)
    if shape_override:
        shape, shape_reason = shape_override, "chosen manually"
    else:
        shape, shape_reason = select_shape(job_details)
    result["cl_shape"] = shape
    result["cl_shape_reason"] = shape_reason

    # Build cover letter
    cl_text = generate_cover_letter(
        jd_text, cv_text, job_title, company_name, client,
        missing_keywords=missing_keywords,
        gaps=gaps,
        shape=shape
    )

    cl_filename = cover_letter_filename(job_title, company_name)
    cl_path = os.path.join(output_dir, cl_filename)
    build_cover_letter_docx(cl_text, job_title, company_name, cl_path)

    result["cl_path"] = cl_path
    result["cl_filename"] = cl_filename

    return result


def render_batch_result(result, i):
    filename = result["filename"]
    if result["status"] == "FAIL":
        st.error(f"❌ FAIL — {filename}")
        st.caption(f"Reason: {result['stop_reason']}")
        return

    label = f"{result['job_title']} at {result['company_name']} (keyword: {result['keyword_score']}/10)"
    if result["status"] == "BORDERLINE":
        st.warning(f"⚠️ BORDERLINE — {label}")
        st.caption(f"Note: {result['stop_reason']}")
    else:
        st.success(f"✅ PASS — {label}")

    if result.get("cl_shape"):
        st.caption(f"Letter style: {format_shape_name(result['cl_shape'])} ({result['cl_shape_reason']})")

    col1, col2, col3 = st.columns(3)
    with col1:
        download_button("⬇ Download CV", result["cv_path"], result["cv_filename"], key=f"cv_{i}")
    with col2:
        download_button("⬇ Download ATS CV", result["cv_ats_path"], result["cv_ats_filename"], key=f"cv_ats_{i}")
    with col3:
        download_button("⬇ Download Cover Letter", result["cl_path"], result["cl_filename"], key=f"cl_{i}")


def save_batch_summary(batch_log, passed, failed, borderline):
    timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M")
    summary_lines = [
        "BATCH SUMMARY",
        f"Run: {datetime.now().strftime('%d %B %Y, %H:%M')}",
        "=" * 40, ""
    ]
    for r in batch_log:
        label = f"{r['job_title']} @ {r['company_name']}"
        score = f"  (keyword: {r['keyword_score']}/10)" if r['keyword_score'] is not None else ""
        style = f"  [letter: {r['cl_shape']}]" if r.get("cl_shape") else ""
        if r["status"] == "PASS":
            summary_lines.append(f"PASS       {label}{score}{style}")
        elif r["status"] == "FAIL":
            summary_lines.append(f"FAIL       {r['filename']}")
            summary_lines.append(f"  Reason: {r['stop_reason']}")
        else:
            summary_lines.append(f"BORDERLINE {label}{score}{style}")
            summary_lines.append(f"  Note: {r['stop_reason']}")
        summary_lines.append("")

    summary_lines += [
        "-" * 40,
        f"Total: {len(batch_log)}",
        f"Passed: {len(passed)}",
        f"Failed: {len(failed)}",
        f"Borderline: {len(borderline)}"
    ]

    summary_dir = os.path.join(OUTPUTS_DIR, "batch-summaries")
    os.makedirs(summary_dir, exist_ok=True)
    summary_path = os.path.join(summary_dir, f"batch_summary_{timestamp}.txt")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write('\n'.join(summary_lines))
    return summary_path


# --- Initialise session state ---
def init_state():
    defaults = {
        "stage": "input",
        "jd_text": "",
        "mode": None,
        "stress_report": None,
        "keyword_report": None,
        "job_title": None,
        "company_name": None,
        "job_details": None,
        "output_dir": None,
        "cv_path": None,
        "cv_ats_path": None,
        "cl_path": None,
        "cl_text": None,
        "cl_shape": None,
        "cl_shape_reason": None,
        "missing_keywords": [],
        "gaps": "",
        "filename_base": None,
        "cl_filename": None,
        "batch_results": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# --- Sidebar ---
st.sidebar.title("CV Tailor")
st.sidebar.markdown("AI-powered job application pipeline")
st.sidebar.markdown("---")

mode = st.sidebar.radio(
    "What would you like to do?",
    [
        "Full Run",
        "Stress Test only",
        "Keyword Match only",
        "Tailor CV only",
        "Cover Letter only",
    ]
)

# Cover letter style: Auto picks a shape from the role's classification
# (seniority, how specific the JD is, agency-posted or not). Choosing a
# specific style forces it for the next run, including every JD in a batch.
shape_options = {"Auto": None}
for _shape in list_shapes():
    shape_options[format_shape_name(_shape)] = _shape

shape_choice = st.sidebar.selectbox(
    "Cover letter style",
    list(shape_options.keys()),
    help="Auto chooses a style based on the role. Pick one to force it."
)
letter_shape_override = shape_options[shape_choice]

st.sidebar.markdown("---")

if st.sidebar.button("🔄 Reset / New JD"):
    reset_session()

st.sidebar.caption(f"Outputs → {OUTPUTS_DIR}")


# ================================================================
# SINGLE JD — one function per stage. Each stage stores its results in
# session state only after the whole step succeeds, so a failed step can
# simply be retried.
# ================================================================

def stage_input():
    st.subheader("Job Description")
    jd_text = st.text_area(
        "Paste the job description here",
        height=300,
        placeholder="Paste the full job description..."
    )

    if st.button("▶ Run", type="primary", disabled=not jd_text.strip()):
        st.session_state.jd_text = jd_text
        st.session_state.mode = mode
        st.session_state.stage = (
            "stress_test" if mode in ["Full Run", "Stress Test only"]
            else "keyword_match" if mode == "Keyword Match only"
            else "extract_details"
        )
        st.rerun()


def stage_stress_test():
    st.subheader("Job Description")
    st.info(st.session_state.jd_text[:300] + "...")

    if st.session_state.stress_report is None:
        try:
            with st.spinner("Running stress test..."):
                st.session_state.stress_report = run_stress_test(
                    st.session_state.jd_text, get_client()
                )
        except Exception as e:
            show_step_error("Stress test", e)
            return

    st.subheader("Stress Test Report")
    render_stress_report(st.session_state.stress_report)
    overall = st.session_state.stress_report["overall"]

    if overall == "FAIL":
        st.error("Role failed stress test. No documents will be generated.")
        if st.button("🔄 Start over with a new JD"):
            reset_session()

    elif overall == "BORDERLINE":
        st.markdown("---")
        st.warning("This role is borderline. Would you like to proceed?")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Yes, proceed", type="primary"):
                st.session_state.stage = (
                    "done" if st.session_state.mode == "Stress Test only"
                    else "keyword_match"
                )
                st.rerun()
        with col2:
            if st.button("❌ No, stop here"):
                reset_session()

    else:
        if st.session_state.mode == "Stress Test only":
            if st.button("🔄 Start over with a new JD"):
                reset_session()
        else:
            st.session_state.stage = "keyword_match"
            st.rerun()


def stage_keyword_match():
    if st.session_state.stress_report:
        st.subheader("Stress Test Report")
        render_stress_report(st.session_state.stress_report)
        st.markdown("---")

    if st.session_state.keyword_report is None:
        try:
            with st.spinner("Running keyword match..."):
                report = run_keyword_match(
                    st.session_state.jd_text, read_cv_text(), get_client()
                )
        except Exception as e:
            show_step_error("Keyword match", e)
            return
        st.session_state.missing_keywords = report["missing_keywords"]
        st.session_state.gaps = report["gaps"]
        st.session_state.keyword_report = report

    st.subheader("Keyword Match Report")
    render_keyword_report(st.session_state.keyword_report)
    score = st.session_state.keyword_report["score"]

    if st.session_state.mode == "Keyword Match only":
        if st.button("🔄 Start over with a new JD"):
            reset_session()

    elif score <= 6:
        st.markdown("---")
        label = f"Keyword score is {'low' if score <= 3 else 'moderate'} ({score}/10). Proceed anyway?"
        st.warning(label)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Yes, proceed", type="primary"):
                st.session_state.stage = "extract_details"
                st.rerun()
        with col2:
            if st.button("❌ No, stop here"):
                reset_session()
    else:
        st.session_state.stage = "extract_details"
        st.rerun()


def stage_extract_details():
    if st.session_state.job_title is None:
        try:
            with st.spinner("Extracting job details..."):
                job_details = extract_job_details(st.session_state.jd_text, get_client())
                output_dir = make_output_dir(job_details["job_title"], job_details["company_name"])
        except Exception as e:
            show_step_error("Extracting job details", e)
            return
        st.session_state.job_details = job_details
        st.session_state.output_dir = output_dir
        st.session_state.company_name = job_details["company_name"]
        st.session_state.job_title = job_details["job_title"]

    st.session_state.stage = (
        "tailor_cv" if st.session_state.mode in ["Full Run", "Tailor CV only"]
        else "cover_letter"
    )
    st.rerun()


def stage_tailor_cv():
    render_earlier_reports()

    if st.session_state.cv_path is None:
        try:
            with st.spinner("Tailoring CV (this may take 30 seconds)..."):
                structure = load_cv_structure()
                sections = extract_cv_sections(CV_PATH, structure)
                tailored = tailor_with_claude(
                    sections, st.session_state.jd_text, get_client(), structure,
                    missing_keywords=st.session_state.missing_keywords,
                    gaps=st.session_state.gaps
                )
                paths = build_cv_documents(
                    sections, structure, tailored,
                    st.session_state.job_title, st.session_state.company_name,
                    st.session_state.output_dir,
                )
        except Exception as e:
            show_step_error("Tailoring the CV", e)
            return
        st.session_state.filename_base = paths["filename_base"]
        st.session_state.cv_ats_path = paths["cv_ats_path"]
        st.session_state.cv_path = paths["cv_path"]

    render_cv_downloads("tailor")

    if st.session_state.mode == "Full Run":
        st.session_state.stage = "cover_letter"
        st.rerun()
    else:
        if st.button("🔄 Start over with a new JD"):
            reset_session()


def stage_cover_letter():
    render_earlier_reports()

    if st.session_state.cv_path:
        render_cv_downloads("final")
        st.markdown("---")

    if st.session_state.cl_path is None:
        try:
            with st.spinner("Generating cover letter..."):
                # Forced style from the sidebar, or automatic from the role's classification
                if letter_shape_override:
                    shape, shape_reason = letter_shape_override, "chosen manually"
                else:
                    shape, shape_reason = select_shape(st.session_state.job_details)

                cl_text = generate_cover_letter(
                    st.session_state.jd_text, read_cv_text(),
                    st.session_state.job_title, st.session_state.company_name,
                    get_client(),
                    missing_keywords=st.session_state.missing_keywords,
                    gaps=st.session_state.gaps,
                    shape=shape
                )

                cl_filename = cover_letter_filename(
                    st.session_state.job_title, st.session_state.company_name
                )
                cl_path = os.path.join(st.session_state.output_dir, cl_filename)
                build_cover_letter_docx(
                    cl_text,
                    st.session_state.job_title,
                    st.session_state.company_name,
                    cl_path
                )
        except Exception as e:
            show_step_error("Generating the cover letter", e)
            return
        st.session_state.cl_shape = shape
        st.session_state.cl_shape_reason = shape_reason
        st.session_state.cl_text = cl_text
        st.session_state.cl_filename = cl_filename
        st.session_state.cl_path = cl_path

    st.subheader("Cover Letter")
    st.success("✅ Cover letter generated")
    if st.session_state.cl_shape:
        st.caption(
            f"Letter style: {format_shape_name(st.session_state.cl_shape)} "
            f"({st.session_state.cl_shape_reason})"
        )
    st.markdown(st.session_state.cl_text)

    download_button(
        "⬇ Download Cover Letter",
        st.session_state.cl_path,
        st.session_state.cl_filename,
        key="cl_download",
    )

    st.markdown("---")
    st.success(f"✅ All files saved to: {st.session_state.output_dir}")

    if st.button("🔄 Start over with a new JD"):
        reset_session()


def stage_done():
    """End of a 'Stress Test only' run after a borderline result."""
    render_earlier_reports()
    if st.button("🔄 Start over with a new JD"):
        reset_session()


STAGES = {
    "input": stage_input,
    "done": stage_done,
    "stress_test": stage_stress_test,
    "keyword_match": stage_keyword_match,
    "extract_details": stage_extract_details,
    "tailor_cv": stage_tailor_cv,
    "cover_letter": stage_cover_letter,
}


# ================================================================
# BATCH MODE
# ================================================================

def run_batch(uploaded_files):
    try:
        client = get_client()
        cv_text = read_cv_text()
    except Exception as e:
        st.error(f"Couldn't start the batch: {e}")
        return

    batch_log = []

    for i, uploaded_file in enumerate(uploaded_files):
        filename = uploaded_file.name

        st.markdown("---")
        st.markdown(f"### {i+1}/{len(uploaded_files)}: {filename}")

        # One failing JD (bad file, API error, malformed reply) is recorded
        # as a FAIL and the batch carries on with the next one.
        try:
            jd_text = decode_text_bytes(uploaded_file.getvalue())
            if not jd_text.strip():
                raise ValueError("The file is empty.")
            with st.spinner(f"Processing {filename}..."):
                result = process_single_jd_ui(
                    jd_text, client, cv_text,
                    shape_override=letter_shape_override
                )
        except Exception as e:
            result = new_batch_result()
            result["status"] = "FAIL"
            result["stop_reason"] = f"Processing error: {e}"

        result["filename"] = filename
        batch_log.append(result)
        render_batch_result(result, i)

    # --- Batch Summary ---
    st.markdown("---")
    st.markdown("## Batch Summary")

    passed = [r for r in batch_log if r["status"] == "PASS"]
    failed = [r for r in batch_log if r["status"] == "FAIL"]
    borderline = [r for r in batch_log if r["status"] == "BORDERLINE"]

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total", len(batch_log))
    with col2:
        st.metric("✅ Passed", len(passed))
    with col3:
        st.metric("❌ Failed", len(failed))
    with col4:
        st.metric("⚠️ Borderline", len(borderline))

    try:
        summary_path = save_batch_summary(batch_log, passed, failed, borderline)
        st.success(f"✅ Batch summary saved to: {summary_path}")
    except OSError as e:
        st.warning(f"Couldn't save the batch summary file: {e}")


# --- Tabs ---
tab1, tab2 = st.tabs(["Single JD", "Batch Mode"])

with tab1:
    st.title("CV Tailor")
    STAGES.get(st.session_state.stage, stage_input)()

with tab2:
    st.title("Batch Mode")
    st.markdown("Upload multiple job description files and process them all in one go.")
    st.info("Borderline roles will still generate documents and be flagged clearly in the summary. Only hard FAILs are skipped.")
    if letter_shape_override:
        st.warning(
            f"Cover letter style is set to **{format_shape_name(letter_shape_override)}** in the sidebar, "
            "so every letter in this batch will use it. Set it back to Auto to vary the style by role."
        )

    uploaded_files = st.file_uploader(
        "Upload JD files (.txt)",
        type=["txt"],
        accept_multiple_files=True,
        help="Drag and drop multiple .txt files or click to browse"
    )

    if uploaded_files:
        st.markdown(f"**{len(uploaded_files)} file(s) ready to process:**")
        for f in uploaded_files:
            st.markdown(f"• {f.name}")

        if st.button("▶ Run Batch", type="primary"):
            run_batch(uploaded_files)

    else:
        st.info("Upload one or more .txt job description files above to get started.")
