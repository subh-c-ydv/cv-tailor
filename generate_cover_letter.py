import os
import re
import sys
from docx import Document
from utils import (
    read_jd,
    read_cv_text,
    extract_job_details,
    get_client,
    app_file,
    read_text_file,
    ask_claude,
    make_output_dir,
    cover_letter_filename,
)
from shape_selector import (
    SHAPES_DIR,
    list_shapes,
    select_shape,
    record_shape_used,
)

PROMPT_PATH = app_file("cover_letter_prompt.txt")


def load_shape(shape):
    """Read the instructions for one shape from cover_letter_shapes/."""
    available = list_shapes()
    if shape not in available:
        raise ValueError(
            f"Unknown cover letter shape '{shape}'. "
            f"Available shapes: {', '.join(available) if available else 'none found'}"
        )
    return read_text_file(os.path.join(SHAPES_DIR, f"{shape}.txt")).strip()


def generate_cover_letter(jd_text, cv_text, job_title, company_name, client,
                          missing_keywords=None, gaps=None, shape=None,
                          job_details=None):
    """Generate the cover letter text.

    shape: force a specific shape by name. If None, a shape is chosen by
    weighted random selection based on job_details (the dict returned by
    extract_job_details). If job_details is also None, neutral defaults are
    used, so callers that haven't been updated still get varied letters.

    Callers that want to know which shape was chosen (for display) should call
    shape_selector.select_shape() themselves and pass the result as shape."""
    if shape is None:
        shape, _ = select_shape(job_details)

    prompt = read_text_file(PROMPT_PATH).format(
        jd_text=jd_text,
        cv_text=cv_text,
        job_title=job_title,
        company_name=company_name,
        missing_keywords=', '.join(missing_keywords) if missing_keywords else 'None identified',
        gaps=gaps if gaps else 'None identified',
        shape_instructions=load_shape(shape)
    )

    # ask_claude raises if the letter was cut off, so a truncated letter is
    # never saved as if it were complete.
    letter = ask_claude(client, prompt, max_tokens=2000, what="cover letter")

    record_shape_used(shape)
    return letter


def build_cover_letter_docx(cover_letter_text, job_title, company_name, filename):
    from docx.shared import Pt, RGBColor, Inches

    doc = Document()

    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

    name_para = doc.add_paragraph()
    name_run = name_para.add_run("Subhash Chandra Yadav")
    name_run.bold = True
    name_run.font.size = Pt(20)
    name_run.font.color.rgb = RGBColor(0x1F, 0x2D, 0x3D)
    name_run.font.name = "Calibri"

    contact_para = doc.add_paragraph()
    contact_run = contact_para.add_run(
        "+45 9180 7190  ·  syadav@allthingsagile.net  ·  linkedin.com/in/subhashchandrayadav  ·  Copenhagen, Denmark"
    )
    contact_run.font.size = Pt(9)
    contact_run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
    contact_run.font.name = "Calibri"

    divider = doc.add_paragraph()
    divider_run = divider.add_run("─" * 80)
    divider_run.font.size = Pt(8)
    divider_run.font.color.rgb = RGBColor(0x2E, 0x75, 0xB6)
    divider_run.font.name = "Calibri"
    divider.paragraph_format.space_after = Pt(12)

    role_para = doc.add_paragraph()
    role_run = role_para.add_run(f"Re: {job_title} — {company_name}")
    role_run.bold = True
    role_run.font.size = Pt(11)
    role_run.font.color.rgb = RGBColor(0x1F, 0x2D, 0x3D)
    role_run.font.name = "Calibri"
    role_para.paragraph_format.space_after = Pt(16)

    paragraphs = [p.strip() for p in cover_letter_text.split('\n\n') if p.strip()]

    for para_text in paragraphs:
        p = doc.add_paragraph()
        # Render any **markdown bold** as real bold rather than asterisks
        # (same handling as the CV builders); stray markers are dropped.
        for i, part in enumerate(re.split(r"\*\*(.+?)\*\*", para_text)):
            part = part.replace("**", "")
            if not part:
                continue
            run = p.add_run(part)
            run.bold = i % 2 == 1
            run.font.size = Pt(10.5)
            run.font.name = "Calibri"
            run.font.color.rgb = RGBColor(0x1F, 0x2D, 0x3D)
        p.paragraph_format.space_after = Pt(10)
        p.paragraph_format.line_spacing = Pt(14)

    signoff = doc.add_paragraph()
    signoff_run = signoff.add_run("Kind regards,")
    signoff_run.font.size = Pt(10.5)
    signoff_run.font.name = "Calibri"
    signoff_run.font.color.rgb = RGBColor(0x1F, 0x2D, 0x3D)

    name_sign = doc.add_paragraph()
    name_sign_run = name_sign.add_run("Subhash Chandra Yadav")
    name_sign_run.bold = True
    name_sign_run.font.size = Pt(10.5)
    name_sign_run.font.name = "Calibri"
    name_sign_run.font.color.rgb = RGBColor(0x1F, 0x2D, 0x3D)

    doc.save(filename)


def main(job_title=None, company_name=None, output_dir=None,
         missing_keywords=None, gaps=None, jd_text=None, shape=None,
         job_details=None):

    # Use passed jd_text if provided, otherwise read from file
    if jd_text is None:
        print("\nReading job description...")
        jd_text = read_jd()

    print("Reading CV...")
    cv_text = read_cv_text()

    client = get_client()

    # One extraction call gives the title, company AND the role classification
    # used to choose a shape. It is skipped when everything needed was passed in.
    if job_details is None and (not job_title or not company_name or shape is None):
        print("Extracting job details...")
        job_details = extract_job_details(jd_text, client)

    if not job_title or not company_name:
        job_title = job_details["job_title"]
        company_name = job_details["company_name"]
        print(f"  → {job_title} at {company_name}")

    if output_dir is None:
        output_dir = make_output_dir(job_title, company_name)
    os.makedirs(output_dir, exist_ok=True)

    if shape is None:
        shape, reason = select_shape(job_details)
        print(f"Cover letter shape: {shape} ({reason})")
    else:
        print(f"Cover letter shape: {shape} (specified)")

    print("Generating cover letter...")
    cover_letter_text = generate_cover_letter(
        jd_text, cv_text, job_title, company_name, client,
        missing_keywords=missing_keywords,
        gaps=gaps,
        shape=shape
    )

    filename = os.path.join(output_dir, cover_letter_filename(job_title, company_name))
    build_cover_letter_docx(cover_letter_text, job_title, company_name, filename)

    print(f"\nDone! Cover letter saved to: {filename}")
    return job_title, company_name, output_dir


if __name__ == "__main__":
    # Usage:
    #   python generate_cover_letter.py                 -> shape chosen automatically
    #   python generate_cover_letter.py story_first     -> force a specific shape
    #   python generate_cover_letter.py --list          -> show available shapes
    shape_arg = sys.argv[1] if len(sys.argv) > 1 else None
    if shape_arg in ("-h", "--help", "--list"):
        print("Available shapes:", ", ".join(list_shapes()))
    else:
        main(shape=shape_arg)
