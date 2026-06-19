import anthropic
import os
import json
from docx import Document
from config import CV_PATH, JD_PATH, OUTPUTS_DIR


def extract_cv_sections(docx_path):
    doc = Document(docx_path)

    sections = {
        "header": [],
        "professional_summary": [],
        "professional_experience": [],
        "tables": {}
    }

    current_section = "header"

    for element in doc.element.body:
        if element.tag.endswith('}p'):
            from docx.oxml.ns import qn
            runs = element.findall('.//' + qn('w:t'))
            text = ''.join(r.text or '' for r in runs).strip()

            if not text:
                continue

            if text == "PROFESSIONAL SUMMARY":
                current_section = "professional_summary"
                continue
            elif text == "CORE COMPETENCIES":
                current_section = "core_competencies"
                continue
            elif text == "PROFESSIONAL EXPERIENCE":
                current_section = "professional_experience"
                continue
            elif text == "RECOGNITION & PROFESSIONAL COMMUNITY":
                current_section = "recognition"
                continue
            elif text == "EDUCATION & CERTIFICATIONS":
                current_section = "education"
                continue
            elif text == "TOOLS & METHODOLOGIES":
                current_section = "tools"
                continue
            elif text == "LANGUAGES":
                current_section = "languages"
                continue

            if current_section == "header":
                sections["header"].append(text)
            elif current_section == "professional_summary":
                sections["professional_summary"].append(text)
            elif current_section == "professional_experience":
                sections["professional_experience"].append(text)

        elif element.tag.endswith('}tbl'):
            from docx.oxml.ns import qn
            table_texts = []
            for row in element.findall('.//' + qn('w:tr')):
                row_cells = []
                for cell in row.findall('.//' + qn('w:tc')):
                    cell_runs = cell.findall('.//' + qn('w:t'))
                    cell_text = ''.join(r.text or '' for r in cell_runs).strip()
                    if cell_text:
                        row_cells.append(cell_text)
                if row_cells:
                    table_texts.append(row_cells)

            sections["tables"][current_section] = table_texts

    return sections


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


def tailor_with_claude(sections, jd_text, client):
    summary_text = ' '.join(sections["professional_summary"])
    experience_text = '\n'.join(sections["professional_experience"])

    with open("prompt_config.txt", "r") as f:
        prompt_template = f.read()

    prompt = prompt_template.format(
        jd_text=jd_text,
        summary_text=summary_text,
        experience_text=experience_text
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = message.content[0].text.strip()

    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]

    response_text = response_text.strip()
    return json.loads(response_text)


def main(output_dir=None):
    print("\nReading your CV...")
    sections = extract_cv_sections(CV_PATH)

    print("Reading job description...")
    with open(JD_PATH, "r") as f:
        jd_text = f.read()

    print("Extracting job title and company from JD...")
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    job_details = extract_job_details(jd_text, client)

    job_title = job_details["job_title"]
    company_name = job_details["company_name"]
    print(f"  → {job_title} at {company_name}")

    if output_dir is None:
        folder_name = f"{job_title} @ {company_name}".replace("/", "-")
        output_dir = os.path.join(OUTPUTS_DIR, folder_name)
    os.makedirs(output_dir, exist_ok=True)

    print("Sending to Claude for tailoring (this may take 30 seconds)...")
    tailored = tailor_with_claude(sections, jd_text, client)

    filename_base = f"Subhash_Yadav_{job_title}_{company_name}".replace(" ", "_")

    output_data = {
        "header": sections["header"],
        "professional_summary": tailored["professional_summary"],
        "professional_experience": tailored["professional_experience"],
        "tables": sections["tables"],
        "filename": os.path.join(output_dir, filename_base)
    }

    with open("cv_data.json", "w") as f:
        json.dump(output_data, f, indent=2)

    print("Tailoring done. Building Word document...")
    os.system("node build_docx.js")

    print(f"\nDone! CV saved to: {output_dir}")
    return job_title, company_name, output_dir


if __name__ == "__main__":
    main()