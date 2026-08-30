# CV Tailor

An AI-powered job application pipeline built in Python and Node.js, using the Anthropic Claude API. Designed for senior professionals applying to roles in the Danish job market.

## What it does

CV Tailor automates and quality-gates the job application process. Instead of tailoring a CV and cover letter for every role manually, you paste in a job description and the tool does the heavy lifting — but only after it has determined the role is worth pursuing.

### The pipeline

```
Job Description
      ↓
Gate 1: Stress Test (11 parameters)
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
3. Location — reachable by public transport within ~60 minutes from Ørestad, Copenhagen (covers Greater Copenhagen commuter towns, not just city centre)
4. Education — rules out roles requiring a Masters degree as a must-have
5. Contract type — no part-time or maternity cover
6. Salary — rules out roles below 65,000 DKK/month
7. Seniority — flags junior or overly senior roles
8. JD language — rules out Danish-only job descriptions
9. Language requirement — rules out roles requiring native Danish or other non-English languages
10. Cultural fit — rules out public sector or Danish-market-only organisations
11. Ghost job indicator — flags roles with suspiciously little employer or location detail for on-site or hybrid positions

### Outputs

For each role that clears both gates, the tool generates:

- A tailored CV (.docx) — Professional Summary and Experience rewritten for the specific role, achievements selected from the full pool documented per role based on genuine relevance to the JD
- An ATS-friendly CV (.docx) — same content, tables converted to plain text for reliable parsing by Applicant Tracking Systems (SuccessFactors, Workday, etc.)
- A cover letter (.docx) — warm, concise, Danish market appropriate, calibrated for humility over self-promotion, with variety guardrails to avoid templated-sounding openings/transitions/closings
- A keyword match report (.txt) — score, matching keywords, gaps, recommendation

All outputs land in a named folder: `cv-outputs/Job Title @ Company/`

In batch mode, timestamped batch summaries are saved to `cv-outputs/batch-summaries/`.

---

## Interfaces

### Streamlit UI (primary)

```bash
open ~/scripts/CVTailor.app
```

Runs as a persistent background service — starts automatically on login, always available at `http://localhost:8501`. No terminal required for day-to-day use.

Two tabs:
- **Single JD** — paste one job description, run the full pipeline interactively, download results inline
- **Batch Mode** — drag and drop multiple `.txt` JD files, process them all in sequence, download results as they complete

### Terminal menu (companion)

```bash
python3 menu.py
```

Retained as a fallback interface — same underlying pipeline, 8 menu options.

---

## Project structure

```
cv-tailor/                       <- repo (code only)
├── app.py                       <- Streamlit UI (primary interface)
├── menu.py                      <- terminal menu (companion interface)
├── stress_test.py               <- Gate 1
├── keyword_match.py             <- Gate 2
├── tailor_cv.py                 <- CV tailoring engine
├── generate_cover_letter.py     <- Cover letter generator
├── batch_processor.py           <- Batch mode orchestrator (terminal)
├── build_docx.js                <- Word document builder — formatted version (Node.js)
├── build_docx_ats.js            <- Word document builder — ATS-friendly plain text version (Node.js)
├── utils.py                     <- Shared utilities
├── config.py                    <- Path configuration
├── prompt_config.txt            <- CV tailoring prompt (editable)
├── cover_letter_prompt.txt      <- Cover letter prompt (editable)
├── stress_test_prompt.txt       <- Stress test parameters (editable)
├── keyword_match_prompt.txt     <- Keyword match prompt (editable)
└── cv_structure.txt             <- CV section headings and types (editable)

cv-inputs/                       <- outside repo (private)
├── master_cv.docx               <- your master CV goes here
├── job_description.txt          <- single JD mode (terminal menu)
└── jds/                         <- batch mode — drop JD files here (terminal menu)
    └── archive/                 <- processed JDs moved here automatically

cv-outputs/                      <- outside repo
├── batch-summaries/             <- timestamped batch summary files
│   └── batch_summary_YYYY_MM_DD_HH_MM.txt
└── Job Title @ Company/         <- one folder per role that passed both gates
    ├── Your_Name_Job_Title_Company.docx
    ├── Your_Name_Job_Title_Company_ATS.docx
    ├── Your_Name_Cover_Letter_Job_Title_Company.docx
    └── keyword_match_report.txt

~/scripts/                       <- outside repo — background service management
├── CVTailor.app                 <- launches the Streamlit UI as a background service
├── start_cv_tailor.sh           <- underlying startup script
├── restart_cv_tailor.sh         <- one-command restart after code changes
└── restore_cv_tailor.sh         <- re-registers the login item if it drops after a macOS update
```

---

## Setup

### Prerequisites

- Python 3.9+
- Node.js 18+
- Anthropic API key

### Installation

```bash
git clone https://github.com/subh-c-ydv/cv-tailor.git
cd cv-tailor

pip3 install anthropic python-docx streamlit
npm install docx

echo 'export ANTHROPIC_API_KEY="your-key-here"' >> ~/.zshrc
source ~/.zshrc
```

### Folder setup

```bash
mkdir ../cv-inputs ../cv-outputs ../cv-inputs/jds
# Add your master CV to cv-inputs/ named master_cv.docx
```

### Running as a persistent background service (macOS)

```bash
mkdir -p ~/scripts

cat > ~/scripts/start_cv_tailor.sh << 'EOF'
#!/bin/bash
source ~/.zshrc
cd /path/to/cv-tailor
/path/to/streamlit run app.py --server.port 8501 --server.headless true
EOF
chmod +x ~/scripts/start_cv_tailor.sh

osacompile -o ~/scripts/CVTailor.app /tmp/cvtailor.applescript
osascript -e 'tell application "System Events" to make login item at end with properties {path:"~/scripts/CVTailor.app", hidden:true}'
```

If the background service ever drops after a macOS update, restore it with:

```bash
~/scripts/restore_cv_tailor.sh
```

After any code change, restart the running service with:

```bash
~/scripts/restart_cv_tailor.sh
```

---

## Usage

### Single JD mode (Streamlit)

1. Open `http://localhost:8501`
2. Paste the job description in the **Single JD** tab
3. Choose a mode from the sidebar (Full Run is the most common)
4. Click **▶ Run**
5. Review stress test and keyword match results inline; proceed or stop at borderline points
6. Download the tailored CV, ATS-friendly CV, and cover letter directly from the browser

### Batch mode (Streamlit)

1. Open the **Batch Mode** tab
2. Drag and drop multiple `.txt` JD files, or click to browse and select several
3. Click **▶ Run Batch**
4. Results display one by one as each JD completes — borderline roles still generate documents and are clearly flagged
5. A batch summary with pass/fail/borderline counts is saved automatically

### Terminal menu (companion)

```bash
python3 menu.py
```

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

---

## Configuration

All prompts and structure files are plain text and can be edited without touching any code. Changes take effect on the next run — no restart needed.

| File | Controls |
|---|---|
| `prompt_config.txt` | How Claude tailors the CV — achievement selection, summary tone, attribution integrity rules |
| `cover_letter_prompt.txt` | Tone, humility calibration, variety guardrails, and structure of the cover letter |
| `stress_test_prompt.txt` | Stress test parameters and scoring logic |
| `keyword_match_prompt.txt` | How Claude scores keyword alignment |
| `cv_structure.txt` | CV section headings and types (narrative or table) |

---

## How achievement selection works

The master CV typically holds more documented achievements per role than appear in any single tailored CV. Rather than passing a pre-trimmed, fixed set of bullets to Claude, the full pool of achievements for each role is passed in, and Claude is instructed to select the 2-3 most relevant to the specific job description being tailored for — not simply the first ones listed, and not the same default set every time.

This means the same role can surface different achievements depending on what a given JD emphasises (e.g. technical delivery vs. stakeholder governance), while every achievement used must still be reproduced accurately and attributed to the correct employer — selection changes, facts do not.

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
- `table` — sections preserved exactly as-is in the formatted CV, and converted to plain text in the ATS-friendly CV

Example:

```
NAME | header
PROFESSIONAL SUMMARY | narrative
CORE COMPETENCIES | table
PROFESSIONAL EXPERIENCE | narrative
EDUCATION & CERTIFICATIONS | table
SKILLS | table
LANGUAGES | table
```

Headings must match your CV document exactly, including capitalisation and punctuation. Lines starting with # are treated as comments and ignored.

---

## Anti-hallucination and attribution guardrails

The CV tailoring and cover letter prompts explicitly instruct Claude:

- Only surface experience that genuinely exists in the master CV
- Do not fabricate tools, qualifications, or achievements
- Where gaps are structural, leave them as gaps — a lower keyword score is preferable to an inaccurate CV
- Every achievement or metric referenced must be attributed to the exact employer it occurred under — never cross-attributed to a different company, even a similar or adjacent one
- Selection of which achievements to surface may vary by JD, but the substance, numbers, and attribution of each selected achievement must remain unchanged from the master CV
- Cover letters favour understatement over self-promotion, and acknowledge prior employment at the same company (where applicable) with humility rather than as a leveraged credential
- Cover letters avoid repeating the same opening sentence structure, the same "concrete example" transition phrase, or the same closing line across different letters — each letter should read as written for that specific role, not generated from a fixed template

These are prompt-level controls. Spot-check output periodically, particularly company-to-achievement pairings in cover letters, especially in the first several runs after any prompt change.

---

## Document rendering — experience section parsing

Both `build_docx.js` and `build_docx_ats.js` classify each line of the tailored Professional Experience output by counting pipe-separated (`|`) parts, rather than by matching content patterns:

- **3+ parts** (`Title | Company | Date`) → a full job header on one line — bold title, then a subtitle line with company and date, with a spacer inserted before it (except the very first role)
- **2 parts** (`Company | Date`) → a subtitle-only line, paired with a title-only heading on the line before it (used for the "Earlier Career" block)
- **No pipe, but date-like** (e.g. `Earlier Career (2002 – 2014)`) → a title-only heading, starts a new block
- **Starts with `•` or `-`** → a bullet point

This replaced an earlier content-pattern classifier that broke once job header lines consistently contained both a pipe and a date within the same line — every role was being misread as a subtitle-only line, silently dropping bold titles and inter-role spacing. If experience section formatting ever looks wrong again, check `cv_data.json`'s `professional_experience` array first to confirm the data shape, then verify it against this pipe-count logic.

---

## Naming your output files

Output filenames include the candidate name, job title, and company. Both spaces and forward slashes in company names (e.g. "Ambu A/S") are sanitised automatically to avoid invalid file paths. To change the naming convention, update `filename_base` in `tailor_cv.py` and `app.py`.

---

## Roadmap (v2)

- Automated cross-check step verifying company-to-achievement attribution before download
- JD fetch from URL — paste a link, tool fetches the JD automatically
- LinkedIn workaround via browser extension
- Settings panel to view and edit prompt config files in the browser
- Private remote access via Tailscale — reach the background service from other devices without public hosting
- Hosting on Streamlit Cloud (requires rebuilding file handling — no local filesystem in the cloud, and `build_docx.js`/`build_docx_ats.js` currently depend on Node.js, which Streamlit Cloud does not provide)

---

## Built with

- [Anthropic Claude API](https://anthropic.com) — claude-sonnet-4-6
- [python-docx](https://python-docx.readthedocs.io/) — reading the master CV
- [docx (Node.js)](https://docx.js.org/) — generating Word documents
- [Streamlit](https://streamlit.io/) — browser UI
- Python 3.9 / Node.js 24

---

## Changelog

### v1.4
- Achievement selection changed from a fixed/mechanical trim to genuine JD-driven selection — the full pool of documented achievements per role is now passed to Claude, which selects the 2-3 most relevant per JD rather than defaulting to the same set every time
- Cover letter variety guardrails added — explicit instructions against repeating the same opening structure, "concrete example" transition phrase, or closing line across different letters
- Fixed a significant document rendering bug: job header lines (which legitimately contain both `|` and a date) were being misclassified as subtitle-only lines, silently dropping bold job titles and spacing between roles across the entire Professional Experience section. Line classification now uses pipe-part count instead of content pattern matching, in both `build_docx.js` and `build_docx_ats.js`

### v1.3
- ATS-friendly CV variant added — table sections rendered as plain text for reliable parsing by SuccessFactors, Workday, and similar systems; generated alongside the formatted CV on every successful run
- Stress test location parameter changed from a strict Capital Region boundary to a commute-based radius (~60 minutes by train/metro from Ørestad), correctly including commuter towns like Ballerup
- Cover letter humility calibration — reduced self-promotional language, added acknowledgement pattern for prior employment at the same company
- Attribution integrity guardrails added to both CV tailoring and cover letter prompts — achievements must stay attributed to the correct employer, preventing cross-company misattribution
- Fixed filename generation bug where company names containing "/" (e.g. "Ambu A/S") broke file paths during save
- Background service made more resilient — added `restore_cv_tailor.sh` for recovering the login item after macOS updates, and `restart_cv_tailor.sh` as a one-command restart after code changes
- Fixed missing ATS build call and download button in the Single JD Streamlit flow (was only wired into batch mode initially)

### v1.2
- Streamlit UI added as primary interface — stage-based flow using session state
- Batch Mode tab added to Streamlit UI — drag-and-drop multiple JD uploads, borderline roles proceed automatically and are flagged rather than blocking on interactive prompts
- Streamlit UI configured as a persistent background service on macOS — starts on login, runs at `http://localhost:8501`
- Ghost job indicator added as stress test parameter 11
- Terminal menu retained as companion interface
- Fixed Node.js path resolution issue affecting document generation when running as a background service

### v1.1
- CV structure now configurable via `cv_structure.txt` — no hardcoded section headings
- Master CV filename genericised to `master_cv.docx` — ready for public sharing
- Processed JD files automatically archived to `cv-inputs/jds/archive/` after batch run
- Batch summaries saved to `cv-outputs/batch-summaries/` subfolder
- JD preview shown in terminal menu — always know what is loaded before running
- npm PATH warning resolved

### v1.0
- Stress test — 10 configurable parameters
- Keyword match with gap analysis
- Two-gate pipeline — Stress Test then Keyword Match before building documents
- CV tailoring engine with anti-hallucination guardrails
- Cover letter generator — warm, concise, Danish market appropriate
- Batch mode with interactive borderline processing (terminal)
- Timestamped batch summary saved to cv-outputs/
- Gap injection — missing keywords flow silently into CV and cover letter prompts
- JD context leak fix for batch mode
- Full terminal menu — 8 options