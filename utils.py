import anthropic
import os
import json
import subprocess
import shutil
from docx import Document
from config import JD_PATH, CV_PATH

CV_TAILOR_DIR = os.path.dirname(os.path.abspath(__file__))


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


def extract_job_details(jd_text, client):
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": f"""Extract the job title and company name from this job description.
Return only JSON in exactly this format, no other text:
{{
    "job_title": "the job title",
    "company_name": "the company name"
}}

JOB DESCRIPTION:
{jd_text}"""
        }]
    )

    response_text = message.content[0].text.strip()
    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]
    return json.loads(response_text.strip())