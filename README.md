# CV Tailor

An AI-powered job application pipeline built in Python and Node.js, using the Anthropic Claude API. Designed for senior professionals applying to roles in the Danish job market.

## What it does

CV Tailor automates and quality-gates the job application process. Instead of tailoring a CV and cover letter for every role manually, you paste in a job description and the tool does the heavy lifting — but only after it has determined the role is worth pursuing.

### The pipeline

```
Job Description
      ↓
Gate 1: Stress Test (10 parameters)
      ↓ FAIL → Stop
      ↓ BORDERLINE → Ask user
      ↓ PASS
      ↓
Gate 2: Keyword Match (scored 0-10)
      ↓ 0-3 → Recommend drop, ask user
      ↓ 4-6 → Flag gaps, ask user
      ↓ 7-10 → Auto proceed
      ↓
Tailor CV + Generate Cover Letter
      ↓
Named output folder with all documents
```

### Stress test parameters

1. Remote policy — no remote-only roles
2. Work permit — must not explicitly exclude sponsorship
3. Location — Capital Region of Denmark only
4. Education — rules out roles requiring a Masters degree as a must-have
5. Contract type — no part-time or maternity cover
6. Salary — rules out roles below 65,000 DKK/month
7. Seniority — flags junior or overly senior roles
8. JD language — rules out Danish-only job descriptions
9. Language requirement — rules out roles requiring native Danish or other non-English languages
10. Cultural fit — rules out public sector or Danish-market-only organisations

### Outputs

For each role that clears both gates, the tool generates:

- A tailored CV (.docx) — Professional Summary and Experience rewritten for the specific role, with keyword gaps injected as context
- A cover letter (.docx) — warm, concise, Danish market appropriate
- A keyword match report (.txt) — score, matching keywords, gaps, recommendation

All outputs land in a named folder: `cv-outputs/Job Title @ Company/`

In batch mode, timestamped batch summaries are saved to `cv-outputs/batch-summaries/`.

---

## Project structure

```
cv-tailor/                       <- repo (code only)
├── menu.py                      <- main entry point
├── stress_test.py               <- Gate 1
├── keyword_match.py             <- Gate 2
├── tailor_cv.py                 <- CV tailoring engine
├── generate_cover_letter.py     <- Cover letter generator
├── batch_processor.py           <- Batch mode orchestrator
├── build_docx.js                <- Word document builder (Node.js)
├── utils.py                     <- Shared utilities
├── config.py                    <- Path configuration
├── prompt_config.txt            <- CV tailoring prompt (editable)
├── cover_letter_prompt.txt      <- Cover letter prompt (editable)
├── stress_test_prompt.txt       <- Stress test parameters (editable)
├── keyword_match_prompt.txt     <- Keyword match prompt (editable)
└── cv_structure.txt             <- CV section headings and types (editable)

cv-inputs/                       <- outside repo (private)
├── master_cv.docx               <- your master CV goes here
├── job_description.txt          <- single JD mode
└── jds/                         <- batch mode — drop JD files here
    └── archive/                 <- processed JDs moved here automatically

cv-outputs/                      <- outside repo
├── batch-summaries/             <- timestamped batch summary files
│   └── batch_summary_YYYY_MM_DD_HH_MM.txt
└── Job Title @ Company/         <- one folder per role that passed both gates
    ├── Your_Name_Job_Title_Company.docx
    ├── Your_Name_Cover_Letter_Job_Title_Company.docx
    └── keyword_match_report.txt
```

---

## Setup

### Prerequisites

- Python 3.9+
- Node.js 18+
- Anthropic API key

### Installation

```bash
# Clone the repo
git clone https://github.com/subh-c-ydv/cv-tailor.git
cd cv-tailor

# Install Python dependencies
pip3 install anthropic python-docx

# Install Node.js dependencies
npm install docx

# Set your API key
echo 'export ANTHROPIC_API_KEY="your-key-here"' >> ~/.zshrc
source ~/.zshrc
```

### Folder setup

```bash
# Create input and output folders outside the repo
mkdir ../cv-inputs ../cv-outputs ../cv-inputs/jds

# Add your master CV to cv-inputs/ named master_cv.docx
```

---

## Usage

```bash
python3 menu.py
```

### Menu options

```
1. Stress Test only
2. Keyword Match only
3. Full Run (Stress Test -> Keyword Match -> CV + Cover Letter)
4. Tailor CV only
5. Generate Cover Letter only
6. Both CV + Cover Letter
7. Batch Mode (process all JDs in cv-inputs/jds/)
8. Exit
```

The menu shows a preview of the JD currently loaded in `job_description.txt` so you always know what is queued for single mode before running.

### Single JD mode (options 1-6)

1. Paste your job description into `cv-inputs/job_description.txt`
2. Run `python3 menu.py`
3. Choose option 3 for the full pipeline

### Batch mode (option 7)

1. Drop multiple JD `.txt` files into `cv-inputs/jds/`
2. Run `python3 menu.py`
3. Choose option 7
4. Review the batch summary and optionally process borderline roles interactively
5. Processed JD files are automatically archived to `cv-inputs/jds/archive/`

---

## Configuration

All prompts and structure files are plain text and can be edited without touching any code:

| File | Controls |
|---|---|
| `prompt_config.txt` | How Claude tailors the CV |
| `cover_letter_prompt.txt` | Tone and structure of the cover letter |
| `stress_test_prompt.txt` | Stress test parameters and scoring logic |
| `keyword_match_prompt.txt` | How Claude scores keyword alignment |
| `cv_structure.txt` | CV section headings and types (narrative or table) |

---

## Adapting to your CV structure

CV Tailor reads your CV section headings from `cv_structure.txt`. Edit this file to match your own CV exactly.

Each line follows this format:

```
SECTION HEADING | type
```

Three types are supported:

- `header` — your name and contact info block (always first)
- `narrative` — sections Claude will tailor (summary, experience)
- `table` — sections preserved exactly as-is (skills, education, certifications, etc.)

Example for a standard CV:

```
NAME | header
PROFESSIONAL SUMMARY | narrative
CORE COMPETENCIES | table
PROFESSIONAL EXPERIENCE | narrative
EDUCATION & CERTIFICATIONS | table
SKILLS | table
LANGUAGES | table
```

Headings must match your CV document exactly, including capitalisation and punctuation.
Lines starting with # are treated as comments and ignored.

---

## Anti-hallucination guardrails

The CV tailoring and cover letter prompts explicitly instruct Claude:

- Only surface experience that genuinely exists in the master CV
- Do not fabricate tools, qualifications, or achievements
- Where gaps are structural, leave them as gaps — a lower keyword score is preferable to an inaccurate CV

---

## Naming your output files

By default, output files include the candidate name in the filename. To change this, update the `filename_base` variable in `tailor_cv.py` and `generate_cover_letter.py`:

```python
filename_base = f"Your_Name_{job_title}_{company_name}".replace(" ", "_")
```

---

## Roadmap (v2)

- JD fetch from URL — paste a link, tool fetches the JD automatically
- LinkedIn workaround via browser extension
- Streamlit UI wrapper — browser-based interface
- Multi-user support

---

## Built with

- [Anthropic Claude API](https://anthropic.com) — claude-sonnet-4-6
- [python-docx](https://python-docx.readthedocs.io/) — reading the master CV
- [docx (Node.js)](https://docx.js.org/) — generating Word documents
- Python 3.9 / Node.js 24

---

## Changelog

### v1.1
- CV structure now configurable via `cv_structure.txt` — no hardcoded section headings
- Master CV filename genericised to `master_cv.docx` — ready for public sharing
- Processed JD files automatically archived to `cv-inputs/jds/archive/` after batch run
- Batch summaries saved to `cv-outputs/batch-summaries/` subfolder
- JD preview shown in menu — always know what is loaded before running
- npm PATH warning resolved
- README updated with full changelog and adapter instructions

### v1.0
- Stress test — 10 configurable parameters
- Keyword match with gap analysis
- Two-gate pipeline — Stress Test then Keyword Match before building documents
- CV tailoring engine with anti-hallucination guardrails
- Cover letter generator — warm, concise, Danish market appropriate
- Batch mode with interactive borderline processing
- Timestamped batch summary saved to cv-outputs/
- Gap injection — missing keywords flow silently into CV and cover letter prompts
- JD context leak fix for batch mode
- Full menu — 8 options