import streamlit as st
import os
import json
import anthropic
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

# --- Main area ---
st.title("CV Tailor")

# --- STAGE: INPUT ---
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
        st.session_state.stage = "stress_test" if mode in ["Full Run", "Stress Test only"] else "keyword_match" if mode == "Keyword Match only" else "extract_details"
        st.rerun()

# --- STAGE: STRESS TEST ---
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
                if st.session_state.mode == "Stress Test only":
                    st.session_state.stage = "done"
                else:
                    st.session_state.stage = "keyword_match"
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

# --- STAGE: KEYWORD MATCH ---
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

# --- STAGE: EXTRACT JOB DETAILS ---
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

    next_stage = "tailor_cv" if st.session_state.mode in ["Full Run", "Tailor CV only"] else "cover_letter"
    st.session_state.stage = next_stage
    st.rerun()

# --- STAGE: TAILOR CV ---
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

            filename_base = f"Subhash_Yadav_{st.session_state.job_title}_{st.session_state.company_name}".replace(" ", "_")
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

            os.system("node build_docx.js")
            st.session_state.cv_path = os.path.join(
                st.session_state.output_dir, f"{filename_base}.docx"
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

    if st.session_state.mode == "Full Run":
        st.session_state.stage = "cover_letter"
        st.rerun()
    else:
        if st.button("🔄 Start over with a new JD"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

# --- STAGE: COVER LETTER ---
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

            cl_filename = f"Subhash_Yadav_Cover_Letter_{st.session_state.job_title}_{st.session_state.company_name}.docx".replace(" ", "_")
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