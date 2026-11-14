import os
import re
import json
import tempfile
from docx import Document
from docx.oxml.ns import qn
from utils import (
    app_file,
    read_text_file,
    load_prompt,
    ask_claude_json,
    cv_filename_base,
    run_node_build,
)


def load_cv_structure():
    """Load CV section structure from cv_structure.txt"""
    structure = {
        "header_key": "header",
        "narrative_sections": [],
        "table_sections": [],
        "section_map": {}
    }

    for line in read_text_file(app_file("cv_structure.txt")).splitlines():
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


def normalize_text(text):
    """Collapse repeated whitespace and strip stray leading/trailing
    pipe separators that can appear when a source paragraph starts or
    ends with a tab character (converted to ' | ' during extraction)."""
    if not text:
        return text
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'^(\s*\|\s*)+', '', text)
    text = re.sub(r'(\s*\|\s*)+$', '', text)
    return text.strip()


def get_paragraph_text(element):
    """Extract paragraph text, converting tab characters to a visible
    separator. Word tab elements don't render as spacing when written
    as a raw \\t inside a docx TextRun, so we convert to ' | ' at
    extraction time instead (matches the style already used in the
    tagline, e.g. 'Software Delivery Leadership | Programme...')."""
    parts = []
    for node in element.iter():
        if node.tag == qn('w:t'):
            parts.append(node.text or '')
        elif node.tag == qn('w:tab'):
            parts.append(' | ')
    return normalize_text(''.join(parts))


def get_cell_text(cell):
    """Extract table cell text, converting tab characters to a visible separator."""
    parts = []
    for node in cell.iter():
        if node.tag == qn('w:t'):
            parts.append(node.text or '')
        elif node.tag == qn('w:tab'):
            parts.append(' | ')
    return normalize_text(''.join(parts))


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
            text = get_paragraph_text(element)

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
            table_texts = []
            for row in element.findall('.//' + qn('w:tr')):
                row_cells = []
                for cell in row.findall('.//' + qn('w:tc')):
                    cell_text = get_cell_text(cell)
                    if cell_text:
                        row_cells.append(cell_text)
                if row_cells:
                    table_texts.append(row_cells)

            if current_section in structure["table_sections"]:
                sections["tables"][current_key] = table_texts

    if not sections["header"]:
        raise ValueError(
            f"No header lines (name, tagline, contact) were found in {docx_path}. "
            "Check that the master CV starts with your name and that the section "
            "headings in cv_structure.txt match the CV exactly."
        )

    return sections


def format_competencies_for_prompt(rows):
    """Render the full core competencies pool as readable numbered text
    for the prompt, so Claude can select/reorder from it."""
    lines = []
    for i, row in enumerate(rows, 1):
        label = row[0] if len(row) > 0 else ''
        desc = row[1] if len(row) > 1 else ''
        lines.append(f"{i}. {label} — {desc}")
    return '\n'.join(lines)


def normalise_tailored(raw):
    """Validate the tailoring JSON. The summary and experience are required;
    the tagline and core competencies are optional and fall back to the
    master CV's originals when missing or malformed."""
    summary = raw.get("professional_summary")
    if isinstance(summary, list):
        summary = " ".join(str(s) for s in summary)
    summary = str(summary or "").strip()
    if not summary:
        raise ValueError("The tailoring response had no professional_summary.")

    experience = raw.get("professional_experience")
    if isinstance(experience, str):
        experience = experience.splitlines()
    if not isinstance(experience, list):
        experience = []
    experience = [str(line) for line in experience if str(line).strip()]
    if not experience:
        raise ValueError("The tailoring response had no professional_experience.")

    tagline = raw.get("tagline")
    tagline = str(tagline).strip() if isinstance(tagline, str) else ""

    competencies = []
    for row in raw.get("core_competencies") or []:
        if isinstance(row, (list, tuple)) and row:
            label = str(row[0]).strip()
            desc = str(row[1]).strip() if len(row) > 1 else ""
            if label:
                competencies.append([label, desc])

    return {
        "tagline": tagline,
        "professional_summary": summary,
        "professional_experience": experience,
        "core_competencies": competencies,
    }


def tailor_with_claude(sections, jd_text, client, structure,
                       missing_keywords=None, gaps=None):
    """Send narrative and tailorable sections to Claude for tailoring"""

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

    # Tagline — second line of the header block (index 0 = name)
    header_lines = sections.get("header", [])
    tagline_text = header_lines[1] if len(header_lines) > 1 else ''

    # Core competencies — full pool, formatted for the prompt
    core_competencies_rows = sections.get("tables", {}).get("core_competencies", [])
    core_competencies_text = format_competencies_for_prompt(core_competencies_rows)

    prompt = load_prompt("prompt_config.txt").format(
        jd_text=jd_text,
        tagline_text=tagline_text,
        core_competencies_text=core_competencies_text,
        summary_text=summary_text,
        experience_text=experience_text,
        missing_keywords=', '.join(missing_keywords) if missing_keywords else 'None identified',
        gaps=gaps if gaps else 'None identified'
    )

    raw = ask_claude_json(client, prompt, max_tokens=8192, what="CV tailoring")
    return normalise_tailored(raw)


def build_cv_documents(sections, structure, tailored, job_title, company_name, output_dir):
    """Write the tailored CV as both the styled and the ATS-friendly .docx.

    This is the single place where Claude's tailoring is merged into the
    master CV (tagline, core competencies, summary, experience), so the
    single-JD and batch flows produce exactly the same document.

    Returns a dict with filename_base, cv_path and cv_ats_path."""
    filename_base = cv_filename_base(job_title, company_name)

    # header[0]=name stays, header[1]=tagline is replaced with the tailored
    # one, header[2:]=contact lines stay unchanged
    header_lines = list(sections["header"])
    tailored_tagline = normalize_text(tailored.get("tagline", ""))
    if tailored_tagline and len(header_lines) > 1:
        header_lines[1] = tailored_tagline

    # Use the tailored core competencies, falling back to the original full
    # table if Claude didn't return anything usable
    tables = dict(sections["tables"])
    if tailored.get("core_competencies"):
        tables["core_competencies"] = tailored["core_competencies"]

    output_data = {
        "header": header_lines,
        "professional_summary": tailored["professional_summary"],
        "professional_experience": tailored["professional_experience"],
        "tables": tables,
        "filename": os.path.join(output_dir, filename_base),
        "structure": {
            "narrative_sections": structure["narrative_sections"],
            "table_sections": structure["table_sections"],
            "section_map": structure["section_map"]
        }
    }

    # Each build gets its own temporary data file, so two runs can never
    # overwrite each other's input, and nothing is left behind afterwards.
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json",
                                     prefix="cv_data_", delete=False) as f:
        json.dump(output_data, f, indent=2)
        data_path = f.name
    try:
        run_node_build("build_docx.js", data_path)
        run_node_build("build_docx.js", data_path, "--ats")
    finally:
        os.remove(data_path)

    paths = {
        "filename_base": filename_base,
        "cv_path": os.path.join(output_dir, f"{filename_base}.docx"),
        "cv_ats_path": os.path.join(output_dir, f"{filename_base}_ATS.docx"),
    }
    for key in ("cv_path", "cv_ats_path"):
        if not os.path.exists(paths[key]):
            raise RuntimeError(f"The document builder reported success but {paths[key]} was not created.")
    return paths
