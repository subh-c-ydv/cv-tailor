import os
import time

import streamlit as st

import keyword_match
import pipeline
import stress_test
import utils
from config import OUTPUTS_DIR
from shape_selector import list_shapes

# --- Page config ---
st.set_page_config(
    page_title="CV Tailor",
    page_icon="📄",
    layout="wide"
)

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


# ================================================================
# Helpers
# ================================================================

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
    on_click="ignore" stops the click from rerunning the app."""
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


def document_downloads(documents, key_prefix):
    """Download buttons for one application's CV, ATS CV and cover letter."""
    cv, letter = documents["cv"], documents["letter"]
    col1, col2, col3 = st.columns(3)
    with col1:
        download_button("⬇ Download CV", cv["cv_path"],
                        os.path.basename(cv["cv_path"]), key=f"{key_prefix}_cv")
    with col2:
        download_button("⬇ Download ATS CV", cv["cv_ats_path"],
                        os.path.basename(cv["cv_ats_path"]), key=f"{key_prefix}_ats")
    with col3:
        download_button("⬇ Download Cover Letter", letter["path"],
                        letter["filename"], key=f"{key_prefix}_cl")


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


# --- Initialise session state ---
def init_state():
    defaults = {
        # Single JD
        "stage": "input",
        "jd_text": "",
        "mode": None,
        "stress_report": None,
        "keyword_report": None,
        "job_details": None,
        "job_title": None,
        "company_name": None,
        "output_dir": None,
        "cv": None,
        "letter": None,
        # Batch
        "batch_results": [],
        "batch_summary_path": None,
        "batch_summary_error": None,
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
# simply be retried. The steps themselves live in pipeline.py.
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
                st.session_state.stress_report = stress_test.run_stress_test(
                    st.session_state.jd_text, utils.get_client()
                )
        except Exception as e:
            show_step_error("Stress test", e)
            return

    st.subheader("Stress Test Report")
    render_stress_report(st.session_state.stress_report)
    overall = st.session_state.stress_report["overall"]

    if overall == pipeline.FAIL:
        st.error("Role failed stress test. No documents will be generated.")
        if st.button("🔄 Start over with a new JD"):
            reset_session()

    elif overall == pipeline.BORDERLINE:
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
                st.session_state.keyword_report = keyword_match.run_keyword_match(
                    st.session_state.jd_text, utils.read_cv_text(), utils.get_client()
                )
        except Exception as e:
            show_step_error("Keyword match", e)
            return

    st.subheader("Keyword Match Report")
    render_keyword_report(st.session_state.keyword_report)
    score = st.session_state.keyword_report["score"]

    if st.session_state.mode == "Keyword Match only":
        if st.button("🔄 Start over with a new JD"):
            reset_session()

    elif score <= pipeline.KEYWORD_REVIEW_MAX:
        st.markdown("---")
        st.warning(f"Keyword score is {pipeline.keyword_band(score)} ({score}/10). Proceed anyway?")
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
    if st.session_state.job_details is None:
        try:
            with st.spinner("Extracting job details..."):
                job_details = pipeline.identify_role(st.session_state.jd_text, utils.get_client())
                output_dir = pipeline.start_application(job_details, st.session_state.keyword_report)
        except Exception as e:
            show_step_error("Extracting job details", e)
            return
        st.session_state.output_dir = output_dir
        st.session_state.job_title = job_details["job_title"]
        st.session_state.company_name = job_details["company_name"]
        st.session_state.job_details = job_details

    st.session_state.stage = (
        "tailor_cv" if st.session_state.mode in ["Full Run", "Tailor CV only"]
        else "cover_letter"
    )
    st.rerun()


def render_cv_downloads(key_suffix):
    cv = st.session_state.cv
    st.subheader("Tailored CV")
    st.success(f"✅ CV generated — {st.session_state.job_title} at {st.session_state.company_name}")
    download_button("⬇ Download Tailored CV", cv["cv_path"],
                    os.path.basename(cv["cv_path"]), key=f"cv_download_{key_suffix}")
    download_button("⬇ Download ATS-friendly CV", cv["cv_ats_path"],
                    os.path.basename(cv["cv_ats_path"]), key=f"cv_ats_download_{key_suffix}")


def stage_tailor_cv():
    render_earlier_reports()

    if st.session_state.cv is None:
        try:
            with st.spinner("Tailoring CV (this may take 30 seconds)..."):
                st.session_state.cv = pipeline.make_cv(
                    st.session_state.jd_text, st.session_state.job_details,
                    st.session_state.output_dir, utils.get_client(),
                    st.session_state.keyword_report,
                )
        except Exception as e:
            show_step_error("Tailoring the CV", e)
            return

    render_cv_downloads("tailor")

    if st.session_state.mode == "Full Run":
        st.session_state.stage = "cover_letter"
        st.rerun()
    else:
        if st.button("🔄 Start over with a new JD"):
            reset_session()


def stage_cover_letter():
    render_earlier_reports()

    if st.session_state.cv:
        render_cv_downloads("final")
        st.markdown("---")

    if st.session_state.letter is None:
        try:
            with st.spinner("Generating cover letter..."):
                st.session_state.letter = pipeline.make_cover_letter(
                    st.session_state.jd_text, utils.read_cv_text(),
                    st.session_state.job_details, st.session_state.output_dir,
                    utils.get_client(), st.session_state.keyword_report,
                    shape=letter_shape_override,
                )
        except Exception as e:
            show_step_error("Generating the cover letter", e)
            return

    letter = st.session_state.letter
    st.subheader("Cover Letter")
    st.success("✅ Cover letter generated")
    st.caption(f"Letter style: {format_shape_name(letter['shape'])} ({letter['shape_reason']})")
    st.markdown(letter["text"])

    download_button("⬇ Download Cover Letter", letter["path"], letter["filename"], key="cl_download")

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
# BATCH MODE — results live in session state, so they stay on screen
# while you review held roles and download documents.
# ================================================================

def run_batch(uploaded_files):
    try:
        client = utils.get_client()
        cv_text = utils.read_cv_text()
    except Exception as e:
        st.error(f"Couldn't start the batch: {e}")
        return

    results = []
    progress = st.progress(0.0)
    for i, uploaded_file in enumerate(uploaded_files):
        progress.progress(i / len(uploaded_files),
                          text=f"Processing {uploaded_file.name} ({i + 1} of {len(uploaded_files)})…")
        results.append(pipeline.process_batch_item(
            uploaded_file.name, uploaded_file.getvalue(), cv_text, client,
            shape=letter_shape_override,
        ))
    progress.empty()

    st.session_state.batch_results = results
    save_batch_summary()
    st.rerun()


def save_batch_summary():
    """Write (or rewrite, after an approval) the batch summary file."""
    try:
        st.session_state.batch_summary_path = pipeline.save_batch_summary(
            st.session_state.batch_results, st.session_state.batch_summary_path
        )
        st.session_state.batch_summary_error = None
    except OSError as e:
        st.session_state.batch_summary_error = str(e)


def approve_held_role(index):
    result = st.session_state.batch_results[index]
    try:
        with st.spinner(f"Generating CV and cover letter for {pipeline.batch_label(result)}…"):
            pipeline.approve_held_role(result, utils.read_cv_text(), utils.get_client(),
                                       shape=letter_shape_override)
        result.pop("approve_error", None)
    except Exception as e:
        result["approve_error"] = str(e)
    save_batch_summary()
    st.rerun()


def role_heading(result):
    details = result["job_details"]
    if details:
        return f"{details['job_title']} at {details['company_name']}  ·  {result['filename']}"
    return result["filename"]


def render_batch_results():
    results = st.session_state.batch_results
    if not results:
        return

    generated = [i for i, r in enumerate(results) if r["documents"]]
    held = [i for i, r in enumerate(results) if pipeline.is_held(r)]
    failed = [i for i, r in enumerate(results) if r["status"] == pipeline.FAIL]

    st.markdown("---")
    st.markdown("## Batch results")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total", len(results))
    col2.metric("✅ Generated", len(generated))
    col3.metric("⏸ Held for review", len(held))
    col4.metric("❌ Failed", len(failed))

    if held:
        st.markdown("### ⏸ Held for review")
        st.caption("These roles were borderline, so nothing has been generated for them yet. "
                   "Read the reports, then generate documents for the ones worth applying to.")
        for i in held:
            r = results[i]
            with st.expander(f"⚠️ {role_heading(r)}", expanded=True):
                for reason in r["reasons"]:
                    st.markdown(f"- {reason}")
                if r.get("approve_error"):
                    st.error(f"Generating documents failed: {r['approve_error']}")
                if st.button("✅ Generate CV & cover letter", type="primary", key=f"approve_{i}"):
                    approve_held_role(i)
                st.markdown("#### Stress test")
                render_stress_report(r["stress_report"])
                if r["keyword_report"]:
                    st.markdown("#### Keyword match")
                    render_keyword_report(r["keyword_report"])

    if generated:
        st.markdown("### ✅ Generated")
        for i in generated:
            r = results[i]
            score = r["keyword_report"]["score"]
            note = "  — approved after review" if r["approved"] else ""
            st.success(f"{role_heading(r)}  (keyword: {score}/10){note}")
            letter = r["documents"]["letter"]
            st.caption(f"Letter style: {format_shape_name(letter['shape'])} ({letter['shape_reason']})")
            document_downloads(r["documents"], key_prefix=f"batch_{i}")

    if failed:
        st.markdown("### ❌ Failed")
        for i in failed:
            r = results[i]
            st.error(role_heading(r))
            for reason in r["reasons"]:
                st.caption(reason)

    if st.session_state.batch_summary_path:
        st.caption(f"Batch summary saved to: {st.session_state.batch_summary_path}")
    if st.session_state.batch_summary_error:
        st.warning(f"Couldn't save the batch summary file: {st.session_state.batch_summary_error}")

    if st.button("🧹 Clear batch results"):
        st.session_state.batch_results = []
        st.session_state.batch_summary_path = None
        st.rerun()


# --- Tabs ---
tab1, tab2 = st.tabs(["Single JD", "Batch Mode"])

with tab1:
    st.title("CV Tailor")
    STAGES.get(st.session_state.stage, stage_input)()

with tab2:
    st.title("Batch Mode")
    st.markdown("Upload multiple job description files and process them all in one go.")
    st.info("Clear passes get a CV and cover letter straight away. Borderline roles are **held for your "
            "review** — nothing is generated for them until you approve. Hard fails are skipped.")
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
    elif not st.session_state.batch_results:
        st.info("Upload one or more .txt job description files above to get started.")

    render_batch_results()
