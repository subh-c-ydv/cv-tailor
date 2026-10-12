import anthropic
import os
import json
import subprocess
import shutil
from docx import Document
from config import JD_PATH, CV_PATH

CV_TAILOR_DIR = os.path.dirname(os.path.abspath(__file__))

# Allowed values for the role classifications returned by extract_job_details().
SENIORITY_TIERS = ("senior", "mid", "junior")
PROBLEM_SPECIFICITY = ("specific", "generic")

# Used only if the model returns a missing or unrecognised value. These are
# deliberately middle-of-the-road so a malformed response never pushes the
# cover letter selection towards an extreme.
DEFAULT_SENIORITY = "senior"
DEFAULT_PROBLEM_SPECIFICITY = "generic"
DEFAULT_AGENCY_POSTED = False


def run_node_build(script_name):
    """
    Run a Node.js build script (e.g. build_docx.js) next to this file,
    regardless of OS or where the process's working directory happens to be.
    Uses 'node' from PATH instead of a hardcoded Mac install location.
    """
    node_exe = shutil.which("node")
    if not node_exe:
        raise RuntimeError(
            "Could not find 'node' on PATH. Install Node.js and make sure "
            "it's available in your terminal/PowerShell before running CV Tailor."
        )

    result = subprocess.run(
        [node_exe, script_name],
        cwd=CV_TAILOR_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{script_name} failed:\n{result.stderr}")
    print(result.stdout)
    return result


def build_word_documents():
    """Run both Node.js document builders (build_docx.js and
    build_docx_ats.js) in an OS-agnostic way. Works from any working
    directory on macOS, Windows, or Linux, as long as Node.js is on
    the system PATH."""
    for script in ["build_docx.js", "build_docx_ats.js"]:
        run_node_build(script)


def read_jd():
    with open(JD_PATH, "r") as f:
        return f.read()


def read_cv_text():
    doc = Document(CV_PATH)
    return '\n'.join([p.text for p in doc.paragraphs if p.text.strip()])


def _normalise_job_details(raw):
    """Turn the model's raw JSON into a clean dict. job_title and
    company_name are required; the role classifications fall back to safe
    defaults if missing or unrecognised."""
    seniority = str(raw.get("seniority_tier", "")).strip().lower()
    if seniority not in SENIORITY_TIERS:
        seniority = DEFAULT_SENIORITY

    specificity = str(raw.get("problem_specificity", "")).strip().lower()
    if specificity not in PROBLEM_SPECIFICITY:
        specificity = DEFAULT_PROBLEM_SPECIFICITY

    agency = raw.get("agency_posted", DEFAULT_AGENCY_POSTED)
    if isinstance(agency, str):
        agency = agency.strip().lower() in ("true", "yes")
    elif not isinstance(agency, bool):
        agency = DEFAULT_AGENCY_POSTED

    return {
        "job_title": raw["job_title"],
        "company_name": raw["company_name"],
        "seniority_tier": seniority,
        "problem_specificity": specificity,
        "agency_posted": agency,
    }


def extract_job_details(jd_text, client):
    """Read the JD once and return the job title and company name, plus three
    classifications used to choose a cover letter shape:
      - seniority_tier: "senior" | "mid" | "junior"
      - problem_specificity: "specific" | "generic"
      - agency_posted: True | False
    Callers that only use job_title and company_name are unaffected."""
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": f"""Analyse this job description and return the details below.

Return only JSON in exactly this format, no other text:
{{
    "job_title": "the job title",
    "company_name": "the company name",
    "seniority_tier": "senior" or "mid" or "junior",
    "problem_specificity": "specific" or "generic",
    "agency_posted": true or false
}}

Definitions:
- company_name: the hiring company. If both a recruitment agency and its client are named, use the client. If the client is not named, use the agency's name.
- seniority_tier: the seniority of the ROLE itself, judged from the title, scope and responsibilities (not from how well any particular candidate would fit). "senior" = senior, lead, head, principal or director-level roles, or roles that shape how the organisation works across several teams. "mid" = an established practitioner or team-level role. "junior" = entry-level, graduate or associate roles.
- problem_specificity: "specific" if the job description describes a concrete situation, challenge or change the role exists to address (for example a transformation under way, a named problem to fix, or a clear description of what is not working today). "generic" if it mainly lists standard responsibilities and requirements without describing a particular situation.
- agency_posted: true if the posting appears to come from a recruitment agency, headhunter or staffing firm rather than the hiring company itself (for example "on behalf of our client", an agency's own name and branding, or an unnamed client company). Otherwise false.

JOB DESCRIPTION:
{jd_text}"""
        }]
    )

    response_text = message.content[0].text.strip()

    # Tolerate markdown code fences or stray text around the JSON object.
    start = response_text.find("{")
    end = response_text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"Could not find JSON in job details response: {response_text[:200]}")

    return _normalise_job_details(json.loads(response_text[start:end + 1]))


if __name__ == "__main__":
    # Quick check: classify the JD in job_description.txt and print the result.
    #   python utils.py
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    details = extract_job_details(read_jd(), client)
    print(json.dumps(details, indent=2, ensure_ascii=False))