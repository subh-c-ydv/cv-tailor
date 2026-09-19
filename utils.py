import anthropic
import os
import json
from docx import Document
from config import JD_PATH, CV_PATH


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

def run_node_build(script_name):
    """
    Run a Node.js build script (e.g. build_docx.js) next to this file,
    regardless of OS or where the process's working directory happens to be.
    Uses 'node' from PATH instead of a hardcoded Mac install location.
    """
    import subprocess
    import shutil

    base_dir = os.path.dirname(os.path.abspath(__file__))
    node_exe = shutil.which("node") or "node"
    result = subprocess.run(
        [node_exe, script_name],
        cwd=base_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[run_node_build] {script_name} failed:\n{result.stderr}")
    return result
