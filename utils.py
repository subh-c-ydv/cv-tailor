import json
import os
import re
import shutil
import subprocess

import anthropic
from docx import Document

from config import APP_DIR, CV_PATH, OUTPUTS_DIR, CLAUDE_MODEL

# Kept under its old name for existing imports (shape_selector, generate_cover_letter).
CV_TAILOR_DIR = APP_DIR

# Allowed values for the role classifications returned by extract_job_details().
SENIORITY_TIERS = ("senior", "mid", "junior")
PROBLEM_SPECIFICITY = ("specific", "generic")

# Used only if the model returns a missing or unrecognised value. These are
# deliberately middle-of-the-road so a malformed response never pushes the
# cover letter selection towards an extreme.
DEFAULT_SENIORITY = "senior"
DEFAULT_PROBLEM_SPECIFICITY = "generic"
DEFAULT_AGENCY_POSTED = False

# Used when the JD doesn't make the title or company clear, so the pipeline
# can still name its output folder instead of crashing.
UNKNOWN_TITLE = "Unknown Role"
UNKNOWN_COMPANY = "Unknown Company"

# Prefix for every generated document's file name.
FILENAME_PREFIX = "Subhash_Yadav"


# ---------------------------------------------------------------------------
# Reading files
# ---------------------------------------------------------------------------

def app_file(name):
    """Absolute path of a file that ships with the app (prompts, configs)."""
    return os.path.join(APP_DIR, name)


def read_text_file(path):
    """Read a text file we control (prompts, configs) as UTF-8. Without an
    explicit encoding, Windows reads them as cp1252 and garbles characters
    such as —, ø and │ before they reach Claude."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_prompt(name):
    return read_text_file(app_file(name))


def decode_text_bytes(data):
    """Decode a JD file whose encoding we don't control. Tries UTF-8 (with or
    without a BOM), then Windows-1252 (what Notepad and Word's 'Plain Text'
    export produce on Windows). Latin-1 decodes any byte, so this never fails."""
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def read_cv_text():
    doc = Document(CV_PATH)
    return '\n'.join([p.text for p in doc.paragraphs if p.text.strip()])


# ---------------------------------------------------------------------------
# Output folder and file names
# ---------------------------------------------------------------------------

# Characters Windows forbids in file names (macOS/Linux forbid only "/").
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{n}" for prefix in ("COM", "LPT") for n in range(1, 10)
}

# Title and company are truncated so the full path stays under Windows'
# 260-character limit, even inside the OneDrive Documents folder.
_MAX_TITLE_LENGTH = 50
_MAX_COMPANY_LENGTH = 30


def safe_filename(text, max_length=80):
    """Make text safe to use in a file or folder name on every OS."""
    text = _INVALID_FILENAME_CHARS.sub("-", str(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    text = text[:max_length].rstrip(". ")  # Windows drops trailing dots/spaces
    if not text:
        return "Untitled"
    if text.upper() in _WINDOWS_RESERVED_NAMES:
        return f"_{text}"
    return text


def _safe_title_and_company(job_title, company_name):
    return (
        safe_filename(job_title, _MAX_TITLE_LENGTH),
        safe_filename(company_name, _MAX_COMPANY_LENGTH),
    )


def make_output_dir(job_title, company_name):
    """Create (if needed) and return the output folder for one application."""
    title, company = _safe_title_and_company(job_title, company_name)
    path = os.path.join(OUTPUTS_DIR, f"{title} @ {company}")
    os.makedirs(path, exist_ok=True)
    return path


def cv_filename_base(job_title, company_name):
    """CV file name without extension (the builders add .docx / _ATS.docx)."""
    title, company = _safe_title_and_company(job_title, company_name)
    return f"{FILENAME_PREFIX}_{title}_{company}".replace(" ", "_")


def cover_letter_filename(job_title, company_name):
    title, company = _safe_title_and_company(job_title, company_name)
    return f"{FILENAME_PREFIX}_Cover_Letter_{title}_{company}.docx".replace(" ", "_")


# ---------------------------------------------------------------------------
# Claude
# ---------------------------------------------------------------------------

def get_client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env in the "
            f"CV Tailor folder ({APP_DIR}) and add your key."
        )
    return anthropic.Anthropic()


def ask_claude(client, prompt, max_tokens, what):
    """Send one prompt and return Claude's text reply. Raises a clear error
    instead of silently returning a cut-off, declined or empty answer.
    `what` names the step in error messages (e.g. "stress test")."""
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )

    if message.stop_reason == "max_tokens":
        raise RuntimeError(
            f"The {what} response was cut off at the {max_tokens}-token limit. "
            "Try again; if it keeps happening, raise max_tokens for this step."
        )
    if message.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined to answer the {what} request.")

    text = "".join(
        block.text for block in message.content if block.type == "text"
    ).strip()
    if not text:
        raise RuntimeError(f"The {what} response was empty.")
    return text


def parse_json_object(text, what):
    """Pull the JSON object out of a reply, tolerating markdown code fences or
    stray text around it."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end < start:
        raise ValueError(f"No JSON found in the {what} response. It began: {text[:200]!r}")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(
            f"The {what} response was not valid JSON ({e}). It began: {text[:200]!r}"
        ) from e


def ask_claude_json(client, prompt, max_tokens, what):
    result = parse_json_object(ask_claude(client, prompt, max_tokens, what), what)
    if not isinstance(result, dict):
        raise ValueError(f"The {what} response was JSON but not an object.")
    return result


# ---------------------------------------------------------------------------
# Node.js document builders
# ---------------------------------------------------------------------------

def run_node_build(script_name, *args, timeout=120):
    """
    Run a Node.js build script (e.g. build_docx.js) next to this file with
    the given arguments, regardless of OS or the current working directory.
    Uses 'node' from PATH instead of a hardcoded Mac install location.
    """
    node_exe = shutil.which("node")
    if not node_exe:
        raise RuntimeError(
            "Could not find 'node' on PATH. Install Node.js and make sure "
            "it's available in your terminal/PowerShell before running CV Tailor."
        )

    try:
        result = subprocess.run(
            [node_exe, script_name, *args],
            cwd=APP_DIR,
            capture_output=True,
            # Node writes UTF-8; Windows would otherwise decode it as cp1252.
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{script_name} did not finish within {timeout} seconds.")

    if result.returncode != 0:
        raise RuntimeError(f"{script_name} failed:\n{result.stderr or result.stdout}")
    return result


# ---------------------------------------------------------------------------
# Job details
# ---------------------------------------------------------------------------

def _clean_name(value, fallback):
    value = str(value or "").strip()
    return value if value and value.lower() not in ("null", "none", "unknown") else fallback


def _normalise_job_details(raw):
    """Turn the model's raw JSON into a clean dict. Missing titles or company
    names fall back to placeholders; the role classifications fall back to
    safe defaults if missing or unrecognised."""
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
        "job_title": _clean_name(raw.get("job_title"), UNKNOWN_TITLE),
        "company_name": _clean_name(raw.get("company_name"), UNKNOWN_COMPANY),
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
    prompt = f"""Analyse this job description and return the details below.

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

    raw = ask_claude_json(client, prompt, max_tokens=500, what="job details")
    return _normalise_job_details(raw)
