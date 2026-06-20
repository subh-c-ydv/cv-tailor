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

In batch mode, a timestamped batch summary is saved to `cv-outputs/`.

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
└── keyword_match_prompt.txt     <- Keyword match prompt (editable)

cv-inputs/                       <- outside repo (private)
├── master_cv.docx               <- your master CV goes here
├── job_description.txt          <- single JD mode
└── jds/                         <- batch mode — drop JD files here

cv-outputs/                      <- outside repo
├── batch_summary_YYYY_MM_DD_HH_MM.txt
└── Job Title @ Company/
    ├── Subhash_Yadav_Job_Title_Company.docx
    ├── Subhash_Yadav_Cover_Letter_Job_Title_Company.docx
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

# Add your master CV to cv-inputs/
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

### Single JD mode

1. Paste your job description into `cv-inputs/job_description.txt`
2. Run `python3 menu.py`
3. Choose option 3 for the full pipeline

### Batch mode

1. Drop multiple JD `.txt` files into `cv-inputs/jds/`
2. Run `python3 menu.py`
3. Choose option 7
4. Review the batch summary and optionally process borderline roles interactively

---

## Configuration

All prompts are stored as plain text files and can be edited without touching any code:

| File | Controls |
|---|---|
| `prompt_config.txt` | How Claude tailors the CV |
| `cover_letter_prompt.txt` | Tone and structure of the cover letter |
| `stress_test_prompt.txt` | Stress test parameters and scoring logic |
| `keyword_match_prompt.txt` | How Claude scores keyword alignment |

---

## Anti-hallucination guardrails

The CV tailoring and cover letter prompts explicitly instruct Claude:

- Only surface experience that genuinely exists in the master CV
- Do not fabricate tools, qualifications, or achievements
- Where gaps are structural, leave them as gaps — a lower keyword score is preferable to an inaccurate CV

---

## Tech debt

- npm PATH warning flagged on initial setup — to be resolved
- JD fetching from URLs (LinkedIn workaround) — planned for v2

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