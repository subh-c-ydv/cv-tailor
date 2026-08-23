from unittest import result

import streamlit as st
import os
import json
import anthropic
from datetime import datetime
from config import OUTPUTS_DIR, CV_PATH
from utils import read_cv_text, extract_job_details
from stress_test import run_stress_test
from keyword_match import run_keyword_match, save_keyword_report
from tailor_cv import extract_cv_sections, tailor_with_claude, load_cv_structure
from generate_cover_letter import generate_cover_letter, build_cover_letter_docx

# --- Page config ---
st.set_page_config(
    page_title="CV Tailor",
    page_icon="📄",
    layout="wide"
)

# --- Helpers ---
def get_client():
    return anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

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

def process_single_jd_ui(jd_text, client, cv_text):
    """Process a single JD through the full pipeline for batch mode.
    Borderline results continue to document generation — no interactive prompts.
    Only hard FAILs stop processing.
    """
    result = {
        "status": "PASS",
        "stop_reason": None,
        "job_title": "Unknown",
        "company_name": "Unknown",
        "keyword_score": None,
        "stress_report": None,
        "keyword_report": None,
        "cv_path": None,
        "cl_path": None,
        "cv_filename": None,
        "cl_filename": None,
        "output_dir": None,
    }

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
    missing_keywords = keyword_report.get("missing_keywords", [])
    gaps = keyword_report.get("gaps", "")

    if score <= 3:
        result["status"] = "FAIL"
        result["stop_reason"] = f"Keyword match too low ({score}/10)"
        return result

    if score <= 6 and result["status"] != "BORDERLINE":
        result["status"] = "BORDERLINE"
        result["stop_reason"] = f"Moderate keyword match ({score}/10)"
        # Continue to generate documents despite borderline

    # Extract job details
    job_details = extract_job_details(jd_text, client)
    job_title = job_details["job_title"]
    company_name = job_details["company_name"]
    result["job_title"] = job_title
    result["company_name"] = company_name

    folder_name = f"{job_title} @ {company_name}".replace("/", "-")
    output_dir = os.path.join(OUTPUTS_DIR, folder_name)
    os.makedirs(output_dir, exist_ok=True)
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

    filename_base = f"Subhash_Yadav_{job_title}_{company_name}".replace(" ", "_").replace("/", "-")
    output_data = {
        "header": sections["header"],
        "professional_summary": tailored["professional_summary"],
        "professional_experience": tailored["professional_experience"],
        "tables": sections["tables"],
        "filename": os.path.join(output_dir, filename_base),
        "structure": {
            "narrative_sections": structure["narrative_sections"],
            "table_sections": structure["table_sections"],
            "section_map": structure["section_map"]
        }
    }

    with open("cv_data.json", "w") as f:
        json.dump(output_data, f, indent=2)

    os.system("cd /Users/subhashyadav/Documents/cv-tailor && /usr/local/bin/node build_docx.js")
    os.system("cd /Users/subhashyadav/Documents/cv-tailor && /usr/local/bin/node build_docx_ats.js")

    cv_path = os.path.join(output_dir, f"{filename_base}.docx")
    result["cv_path"] = cv_path
    result["cv_filename"] = f"{filename_base}.docx"
    result["cv_ats_path"] = os.path.join(output_dir, f"{filename_base}_ATS.docx")
    result["cv_ats_filename"] = f"{filename_base}_ATS.docx"

    # Build cover letter
    cl_text = generate_cover_letter(
        jd_text, cv_text, job_title, company_name, client,
        missing_keywords=missing_keywords,
        gaps=gaps
    )

    cl_filename = f"Subhash_Yadav_Cover_Letter_{job_title}_{company_name}.docx".replace(" ", "_").replace("/", "-")
    cl_path = os.path.join(output_dir, cl_filename)
    build_cover_letter_docx(cl_text, job_title, company_name, cl_path)

    result["cl_path"] = cl_path
    result["cl_filename"] = cl_filename

    return result


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
        "output_dir": None,
        "cv_path": None,
        "cl_path": None,
        "cl_text": None,
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

st.sidebar.markdown("---")

if st.sidebar.button("🔄 Reset / New JD"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

st.sidebar.caption(f"Outputs → {OUTPUTS_DIR}")

# --- Tabs ---
tab1, tab2 = st.tabs(["Single JD", "Batch Mode"])

# ================================================================
# TAB 1 — SINGLE JD
# ================================================================
with tab1:
    st.title("CV Tailor")

    if st.session_state.stage == "input":
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

    elif st.session_state.stage == "stress_test":
        st.subheader("Job Description")
        st.info(st.session_state.jd_text[:300] + "...")

        if st.session_state.stress_report is None:
            with st.spinner("Running stress test..."):
                client = get_client()
                st.session_state.stress_report = run_stress_test(
                    st.session_state.jd_text, client
                )

        st.subheader("Stress Test Report")
        render_stress_report(st.session_state.stress_report)
        overall = st.session_state.stress_report["overall"]

        if overall == "FAIL":
            st.error("Role failed stress test. No documents will be generated.")
            if st.button("🔄 Start over with a new JD"):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()

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
                    for key in list(st.session_state.keys()):
                        del st.session_state[key]
                    st.rerun()

        else:
            if st.session_state.mode == "Stress Test only":
                if st.button("🔄 Start over with a new JD"):
                    for key in list(st.session_state.keys()):
                        del st.session_state[key]
                    st.rerun()
            else:
                st.session_state.stage = "keyword_match"
                st.rerun()

    elif st.session_state.stage == "keyword_match":
        if st.session_state.stress_report:
            st.subheader("Stress Test Report")
            render_stress_report(st.session_state.stress_report)
            st.markdown("---")

        if st.session_state.keyword_report is None:
            with st.spinner("Running keyword match..."):
                client = get_client()
                cv_text = read_cv_text()
                st.session_state.keyword_report = run_keyword_match(
                    st.session_state.jd_text, cv_text, client
                )
                st.session_state.missing_keywords = st.session_state.keyword_report.get("missing_keywords", [])
                st.session_state.gaps = st.session_state.keyword_report.get("gaps", "")

        st.subheader("Keyword Match Report")
        render_keyword_report(st.session_state.keyword_report)
        score = st.session_state.keyword_report["score"]

        if st.session_state.mode == "Keyword Match only":
            if st.button("🔄 Start over with a new JD"):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()

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
                    for key in list(st.session_state.keys()):
                        del st.session_state[key]
                    st.rerun()
        else:
            st.session_state.stage = "extract_details"
            st.rerun()

    elif st.session_state.stage == "extract_details":
        if st.session_state.job_title is None:
            with st.spinner("Extracting job details..."):
                client = get_client()
                job_details = extract_job_details(st.session_state.jd_text, client)
                st.session_state.job_title = job_details["job_title"]
                st.session_state.company_name = job_details["company_name"]
                folder_name = f"{st.session_state.job_title} @ {st.session_state.company_name}".replace("/", "-")
                st.session_state.output_dir = os.path.join(OUTPUTS_DIR, folder_name)
                os.makedirs(st.session_state.output_dir, exist_ok=True)

        next_stage = (
            "tailor_cv" if st.session_state.mode in ["Full Run", "Tailor CV only"]
            else "cover_letter"
        )
        st.session_state.stage = next_stage
        st.rerun()

    elif st.session_state.stage == "tailor_cv":
        if st.session_state.stress_report:
            st.subheader("Stress Test Report")
            render_stress_report(st.session_state.stress_report)
            st.markdown("---")

        if st.session_state.keyword_report:
            st.subheader("Keyword Match Report")
            render_keyword_report(st.session_state.keyword_report)
            st.markdown("---")

        if st.session_state.cv_path is None:
            with st.spinner("Tailoring CV (this may take 30 seconds)..."):
                client = get_client()
                structure = load_cv_structure()
                sections = extract_cv_sections(CV_PATH, structure)
                tailored = tailor_with_claude(
                    sections, st.session_state.jd_text, client, structure,
                    missing_keywords=st.session_state.missing_keywords,
                    gaps=st.session_state.gaps
                )

                filename_base = f"Subhash_Yadav_{st.session_state.job_title}_{st.session_state.company_name}".replace(" ", "_").replace("/", "-")
                st.session_state.filename_base = filename_base

                output_data = {
                    "header": sections["header"],
                    "professional_summary": tailored["professional_summary"],
                    "professional_experience": tailored["professional_experience"],
                    "tables": sections["tables"],
                    "filename": os.path.join(st.session_state.output_dir, filename_base),
                    "structure": {
                        "narrative_sections": structure["narrative_sections"],
                        "table_sections": structure["table_sections"],
                        "section_map": structure["section_map"]
                    }
                }

                with open("cv_data.json", "w") as f:
                    json.dump(output_data, f, indent=2)

                os.system("cd /Users/subhashyadav/Documents/cv-tailor && /usr/local/bin/node build_docx.js")
                os.system("cd /Users/subhashyadav/Documents/cv-tailor && /usr/local/bin/node build_docx_ats.js")
                st.session_state.cv_path = os.path.join(
                    st.session_state.output_dir, f"{filename_base}.docx"
                )
                st.session_state.cv_ats_path = os.path.join(
                    st.session_state.output_dir, f"{filename_base}_ATS.docx"
                )

        st.subheader("Tailored CV")
        st.success(f"✅ CV generated — {st.session_state.job_title} at {st.session_state.company_name}")

        if os.path.exists(st.session_state.cv_path):
            with open(st.session_state.cv_path, "rb") as f:
                st.download_button(
                    label="⬇ Download Tailored CV",
                    data=f,
                    file_name=f"{st.session_state.filename_base}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )

        if st.session_state.get("cv_ats_path") and os.path.exists(st.session_state.cv_ats_path):
            with open(st.session_state.cv_ats_path, "rb") as f:
                st.download_button(
                    label="⬇ Download ATS-friendly CV",
                    data=f,
                    file_name=f"{st.session_state.filename_base}_ATS.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key="cv_ats_download_1"
                )

        if st.session_state.mode == "Full Run":
            st.session_state.stage = "cover_letter"
            st.rerun()
        else:
            if st.button("🔄 Start over with a new JD"):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()

    elif st.session_state.stage == "cover_letter":
        if st.session_state.stress_report:
            st.subheader("Stress Test Report")
            render_stress_report(st.session_state.stress_report)
            st.markdown("---")

        if st.session_state.keyword_report:
            st.subheader("Keyword Match Report")
            render_keyword_report(st.session_state.keyword_report)
            st.markdown("---")

        if st.session_state.cv_path:
            st.subheader("Tailored CV")
            st.success(f"✅ CV generated — {st.session_state.job_title} at {st.session_state.company_name}")

            if os.path.exists(st.session_state.cv_path):
                with open(st.session_state.cv_path, "rb") as f:
                    st.download_button(
                        label="⬇ Download Tailored CV",
                        data=f,
                        file_name=f"{st.session_state.filename_base}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key="cv_download_final"
                    )
            if st.session_state.get("cv_ats_path") and os.path.exists(st.session_state.cv_ats_path):
                with open(st.session_state.cv_ats_path, "rb") as f:
                    st.download_button(
                        label="⬇ Download ATS-friendly CV",
                        data=f,
                        file_name=f"{st.session_state.filename_base}_ATS.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key="cv_ats_download_2"
                    )
            st.markdown("---")

        if st.session_state.cl_path is None:
            with st.spinner("Generating cover letter..."):
                client = get_client()
                cv_text = read_cv_text()
                st.session_state.cl_text = generate_cover_letter(
                    st.session_state.jd_text, cv_text,
                    st.session_state.job_title, st.session_state.company_name,
                    client,
                    missing_keywords=st.session_state.missing_keywords,
                    gaps=st.session_state.gaps
                )

                cl_filename = f"Subhash_Yadav_Cover_Letter_{st.session_state.job_title}_{st.session_state.company_name}.docx".replace(" ", "_").replace("/", "-")
                st.session_state.cl_filename = cl_filename
                cl_path = os.path.join(st.session_state.output_dir, cl_filename)
                build_cover_letter_docx(
                    st.session_state.cl_text,
                    st.session_state.job_title,
                    st.session_state.company_name,
                    cl_path
                )
                st.session_state.cl_path = cl_path

        st.subheader("Cover Letter")
        st.success("✅ Cover letter generated")
        st.markdown(st.session_state.cl_text)

        if os.path.exists(st.session_state.cl_path):
            with open(st.session_state.cl_path, "rb") as f:
                st.download_button(
                    label="⬇ Download Cover Letter",
                    data=f,
                    file_name=st.session_state.cl_filename,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )

        st.markdown("---")
        st.success(f"✅ All files saved to: {st.session_state.output_dir}")

        if st.button("🔄 Start over with a new JD"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

# ================================================================
# TAB 2 — BATCH MODE
# ================================================================
with tab2:
    st.title("Batch Mode")
    st.markdown("Upload multiple job description files and process them all in one go.")
    st.info("Borderline roles will still generate documents and be flagged clearly in the summary. Only hard FAILs are skipped.")

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
            client = get_client()
            cv_text = read_cv_text()
            batch_log = []

            for i, uploaded_file in enumerate(uploaded_files):
                jd_text = uploaded_file.read().decode("utf-8")
                filename = uploaded_file.name

                st.markdown("---")
                st.markdown(f"### {i+1}/{len(uploaded_files)}: {filename}")

                with st.spinner(f"Processing {filename}..."):
                    result = process_single_jd_ui(jd_text, client, cv_text)
                    result["filename"] = filename
                    batch_log.append(result)

                # Display result inline
                if result["status"] == "FAIL":
                    st.error(f"❌ FAIL — {filename}")
                    st.caption(f"Reason: {result['stop_reason']}")

                elif result["status"] == "BORDERLINE":
                    st.warning(f"⚠️ BORDERLINE — {result['job_title']} at {result['company_name']} (keyword: {result['keyword_score']}/10)")
                    st.caption(f"Note: {result['stop_reason']}")
                    col1, col2 = st.columns(2)
                    with col1:
                        if result["cv_path"] and os.path.exists(result["cv_path"]):
                            with open(result["cv_path"], "rb") as f:
                                st.download_button(
                                    label="⬇ Download CV",
                                    data=f,
                                    file_name=result["cv_filename"],
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                    key=f"cv_{i}"
                                )
                    with col2:
                        if result["cl_path"] and os.path.exists(result["cl_path"]):
                            with open(result["cl_path"], "rb") as f:
                                st.download_button(
                                    label="⬇ Download Cover Letter",
                                    data=f,
                                    file_name=result["cl_filename"],
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                    key=f"cl_{i}"
                                )

                else:
                    st.success(f"✅ PASS — {result['job_title']} at {result['company_name']} (keyword: {result['keyword_score']}/10)")
                    col1, col2 = st.columns(2)
                    with col1:
                        if result["cv_path"] and os.path.exists(result["cv_path"]):
                            with open(result["cv_path"], "rb") as f:
                                st.download_button(
                                    label="⬇ Download CV",
                                    data=f,
                                    file_name=result["cv_filename"],
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                    key=f"cv_{i}"
                                )
                    with col2:
                        if result["cl_path"] and os.path.exists(result["cl_path"]):
                            with open(result["cl_path"], "rb") as f:
                                st.download_button(
                                    label="⬇ Download Cover Letter",
                                    data=f,
                                    file_name=result["cl_filename"],
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                    key=f"cl_{i}"
                                )

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

            # Save batch summary file
            timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M")
            summary_lines = [
                "BATCH SUMMARY",
                f"Run: {datetime.now().strftime('%d %B %Y, %H:%M')}",
                "=" * 40, ""
            ]
            for r in batch_log:
                label = f"{r['job_title']} @ {r['company_name']}"
                score = f"  (keyword: {r['keyword_score']}/10)" if r['keyword_score'] else ""
                if r["status"] == "PASS":
                    summary_lines.append(f"PASS       {label}{score}")
                elif r["status"] == "FAIL":
                    summary_lines.append(f"FAIL       {r['filename']}")
                    summary_lines.append(f"  Reason: {r['stop_reason']}")
                else:
                    summary_lines.append(f"BORDERLINE {label}{score}")
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
            with open(summary_path, "w") as f:
                f.write('\n'.join(summary_lines))

            st.success(f"✅ Batch summary saved to: {summary_path}")

    else:
        st.info("Upload one or more .txt job description files above to get started.")