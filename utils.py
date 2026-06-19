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