import anthropic
import os
import json
from docx import Document
from config import CV_PATH, OUTPUTS_DIR
from utils import read_jd, extract_job_details


def load_cv_structure():
    """Load CV section structure from cv_structure.txt"""
    structure = {
        "header_key": "header",
        "narrative_sections": [],
        "table_sections": [],
        "section_map": {}
    }

    with open("cv_structure.txt", "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = [p.strip() for p in line.split("|")]
            if len(parts) != 2:
                continue

            heading, section_type = parts[0], parts[1].lower()

            if section_type == "header":
                structure["section_map"][heading] = "header"
            elif section_type == "narrative":
                structure["narrative_sections"].append(heading)
                structure["section_map"][heading] = heading.lower().replace(" ", "_").replace("&", "and")
            elif section_type == "table":
                structure["table_sections"].append(heading)
                structure["section_map"][heading] = heading.lower().replace(" ", "_").replace("&", "and")

    return structure


def extract_cv_sections(docx_path, structure):
    """Extract text from CV using structure defined in cv_structure.txt"""
    doc = Document(docx_path)

    # Build sections dict dynamically from structure
    sections = {
        "header": [],
        "tables": {}
    }

    # Add narrative sections
    for heading in structure["narrative_sections"]:
        key = structure["section_map"][heading]
        sections[key] = []

    current_section = "header"
    current_key = "header"

    for element in doc.element.body:
        if element.tag.endswith('}p'):
            from docx.oxml.ns import qn
            runs = element.findall('.//' + qn('w:t'))
            text = ''.join(r.text or '' for r in runs).strip()

            if not text:
                continue

            # Check if this line is a section heading
            if text in structure["section_map"]:
                current_section = text
                current_key = structure["section_map"][text]
                continue

            # Add to appropriate section
            if current_key == "header":
                sections["header"].append(text)
            elif current_section in structure["narrative_sections"]:
                sections[current_key].append(text)

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

            if current_section in structure["table_sections"]:
                sections["tables"][current_key] = table_texts

    return sections


def tailor_with_claude(sections, jd_text, client, structure,
                       missing_keywords=None, gaps=None):
    """Send narrative sections to Claude for tailoring"""

    # Build narrative text dynamically from structure
    narrative_texts = {}
    for heading in structure["narrative_sections"]:
        key = structure["section_map"][heading]
        if key in sections:
            narrative_texts[heading] = '\n'.join(sections[key])

    # Build the summary and experience text for the prompt
    summary_key = None
    experience_key = None
    for heading in structure["narrative_sections"]:
        h_lower = heading.lower()
        if "summary" in h_lower:
            summary_key = structure["section_map"][heading]
        if "experience" in h_lower:
            experience_key = structure["section_map"][heading]

    summary_text = ' '.join(sections.get(summary_key, [])) if summary_key else ''
    experience_text = '\n'.join(sections.get(experience_key, [])) if experience_key else ''

    with open("prompt_config.txt", "r") as f:
        prompt_template = f.read()

    prompt = prompt_template.format(
        jd_text=jd_text,
        summary_text=summary_text,
        experience_text=experience_text,
        missing_keywords=', '.join(missing_keywords) if missing_keywords else 'None identified',
        gaps=gaps if gaps else 'None identified'
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


def main(job_title=None, company_name=None, output_dir=None,
         missing_keywords=None, gaps=None, jd_text=None):

    print("\nLoading CV structure...")
    structure = load_cv_structure()

    print("Reading your CV...")
    sections = extract_cv_sections(CV_PATH, structure)

    if jd_text is None:
        print("Reading job description...")
        jd_text = read_jd()

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    if not job_title or not company_name:
        print("Extracting job title and company from JD...")
        job_details = extract_job_details(jd_text, client)
        job_title = job_details["job_title"]
        company_name = job_details["company_name"]
        print(f"  → {job_title} at {company_name}")

    if output_dir is None:
        folder_name = f"{job_title} @ {company_name}".replace("/", "-")
        output_dir = os.path.join(OUTPUTS_DIR, folder_name)
    os.makedirs(output_dir, exist_ok=True)

    print("Sending to Claude for tailoring (this may take 30 seconds)...")
    tailored = tailor_with_claude(
        sections, jd_text, client, structure,
        missing_keywords=missing_keywords,
        gaps=gaps
    )

    filename_base = f"Subhash_Yadav_{job_title}_{company_name}".replace(" ", "_")

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

    print("Tailoring done. Building Word document...")
    os.system("node build_docx.js")

    print(f"\nDone! CV saved to: {output_dir}")
    return job_title, company_name, output_dir


if __name__ == "__main__":
    main()