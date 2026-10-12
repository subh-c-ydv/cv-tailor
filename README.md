# CV Tailor

An AI-powered job application pipeline built in Python and Node.js, using the Anthropic Claude API. Designed for senior professionals applying to roles in the Danish job market.

## What it does

CV Tailor automates and quality-gates the job application process. Instead of tailoring a CV and cover letter for every role manually, you paste in a job description and the tool does the heavy lifting — but only after it has determined the role is worth pursuing.

### The pipeline

```
Job Description
      ↓
Gate 1: Stress Test (12 parameters)
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
3. Location — reachable by public transport (train/metro/bus) within ~60 minutes from Ørestad, Copenhagen (covers Greater Copenhagen commuter towns; explicitly excludes Odense, Aarhus, Aalborg, Vejle, Esbjerg, Horsens and similar)
4. Education — rules out roles requiring a Masters degree as a must-have
5. Contract type — no part-time or maternity cover
6. Salary — rules out roles with a stated base salary band at or below 65,000 DKK/month (excluding pension and bonus)
7. Seniority — flags junior or overly senior roles
8. JD language — rules out Danish-only job descriptions
9. Language requirement — rules out roles requiring native Danish or other non-English languages
10. Cultural fit — rules out public sector or Danish-market-only organisations
11. Ghost job indicator — flags roles with suspiciously little employer or location detail for on-site or hybrid positions
12. Role-type fit — flags pure-strategy, learning & development, or standalone process-excellence individual-contributor roles that fall outside the candidate's actual delivery-focused target

### Outputs

For each role that clears both gates, the tool generates:

- A tailored CV (.docx) — Professional Summary and Experience rewritten for the specific role, achievements selected from the full pool documented per role based on genuine relevance to the JD
- An ATS-friendly CV (.docx) — same content, tables converted to plain text for reliable parsing by Applicant Tracking Systems (SuccessFactors, Workday, etc.)
- A cover letter (.docx) — warm, concise, Danish market appropriate, calibrated for humility over self-promotion. Built from one of several selectable letter structures (see Cover letter shapes), so letters differ in shape as well as wording, and always cover the writer's strengths, how they fit the role, and the value they could add to the team
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
├── shape_selector.py            <- Picks a cover letter shape by weighted random choice
├── batch_processor.py           <- Batch mode orchestrator (terminal)
├── build_docx.js                <- Word document builder — formatted version (Node.js)
├── build_docx_ats.js            <- Word document builder — ATS-friendly plain text version (Node.js)
├── utils.py                     <- Shared utilities
├── config.py                    <- Path configuration
├── prompt_config.txt            <- CV tailoring prompt (editable)
├── cover_letter_prompt.txt      <- Cover letter base prompt: tone, guardrails, rules (editable)
├── cover_letter_shapes/         <- One file per cover letter structure (editable, add your own)
│   ├── problem_first.txt
│   ├── story_first.txt
│   ├── three_strengths.txt
│   ├── direct_short.txt
│   └── question_led.txt
├── cover_letter_weights.txt     <- Which shapes suit which kind of role, and how likely (editable)
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
3. Choose a mode from the sidebar (Full Run is the most common), and optionally a cover letter style (Auto by default)
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
| `prompt_config.txt` | How Claude tailors the CV — achievement selection, summary tone, fixed factual rules, attribution integrity |
| `cover_letter_prompt.txt` | Shared rules for every cover letter — tone, humility calibration, attribution integrity, fixed factual rules, forward-looking rule, variety guardrails, echo-prevention, length and closing |
| `cover_letter_shapes/*.txt` | One file per cover letter structure (paragraph-by-paragraph instructions). Add a new `.txt` file to add a new shape |
| `cover_letter_weights.txt` | Which shapes are eligible for which kind of role (seniority, how specific the JD is, agency-posted or not) and how likely each is |
| `stress_test_prompt.txt` | Stress test parameters and scoring logic |
| `keyword_match_prompt.txt` | How Claude scores keyword alignment |
| `cv_structure.txt` | CV section headings and types (narrative or table) |

---

## How achievement selection works

The master CV typically holds more documented achievements per role than appear in any single tailored CV. Rather than passing a pre-trimmed, fixed set of bullets to Claude, the full pool of achievements for each role is passed in, and Claude is instructed to select the 2-3 most relevant to the specific job description being tailored for — not simply the first ones listed, and not the same default set every time.

This means the same role can surface different achievements depending on what a given JD emphasises (e.g. technical delivery vs. stakeholder governance), while every achievement used must still be reproduced accurately and attributed to the correct employer — selection changes, facts do not.

A narrow, named exception exists for the Collinson Group role (2012–2014): when a JD is genuinely centred on agile practice, delivery enablement, or ways-of-working, that role may surface as its own short entry outside the standard "pre-2015 → Earlier Career" consolidation, since it evidences first-hand early agile experience directly relevant to that specific type of JD.

---

## Fixed factual rules

`prompt_config.txt` and `cover_letter_prompt.txt` both carry a FIXED FACTUAL RULES block — a small set of specific, non-negotiable facts that must hold regardless of how the surrounding text is tailored (e.g. exact tenure dates, precise seniority-level wording, named vendors only, specific metric phrasing, exclusions like a lapsed certification that should never be listed). This sits alongside the general attribution integrity guardrail and exists to lock down well-established, easily-drifted specifics that a general "be accurate" instruction doesn't reliably catch on its own. If you find Claude drifting on a specific fact repeatedly despite the general guardrails, adding it explicitly to this block is the most reliable fix.

---

## Echo-prevention

Both the CV summary and the cover letter are instructed not to mirror the job description's own distinctive phrasing back to the reader. A hiring manager who wrote or knows the JD recognises their own words reflected back, which reads as telling them what they want to hear rather than demonstrating genuine understanding. The substance of what the JD is asking for should still come through — just restated in the candidate's own plain language rather than lifted from the posting.

---

## Cover letter shapes

A cover letter is assembled from two parts: a shared base prompt (`cover_letter_prompt.txt`) holding everything that must hold for every letter, and one *shape* file from `cover_letter_shapes/` that defines the paragraph-by-paragraph structure for that particular letter. The guardrails stay identical across letters while the structure — and therefore how the letter feels — changes.

| Shape | Structure | Designed for |
|---|---|---|
| `problem_first` | Opens with the writer's own read of the role's central challenge, then the strengths that bear on it, then what they would bring | Senior roles where the JD describes a real problem |
| `story_first` | Opens inside one real situation from the CV, then connects it to what the role demands | Senior roles with a generic JD, where experience carries more weight than a described challenge |
| `three_strengths` | Why this role, the three strengths the role weighs most (written as prose, not a list), what the writer would add | Checklist-style JDs and mid-level roles |
| `direct_short` | 120–170 words: fit, evidence and value, close | Recruiter-screened processes |
| `question_led` | Opens with one genuine question the team is probably asking, then the writer's approach to it | Roles with a clear central challenge where a fresh angle helps |

Whatever the shape, every letter must make three things clear: what the writer is genuinely good at (shown through evidence from the master CV, not adjectives), how that connects to what the role demands, and how the writer could add value to the team and the wider organisation.

**Keeping it memorable without being pompous.** The base prompt asks for specificity rather than volume: one vivid, concrete detail (a number, a before/after) instead of several general claims, one plain point of view, varied sentence length, and no superlatives or intensifiers about the writer. Letters target 200–280 words (120–170 for `direct_short`).

**Forward-looking rule.** Any passage about value to the team must be framed as a hypothesis — what the writer would look at or contribute — grounded in experience that actually appears in the master CV. It must never promise specific results or claim insider knowledge of the company.

### How a shape is chosen

By default the shape is chosen automatically, in three steps:

1. **Classify the role.** The extraction call that already reads the JD for the job title and company name also returns three classifications: the seniority of the role (`senior`, `mid`, `junior`), whether the JD describes a concrete situation or challenge (`specific`) or mainly lists standard responsibilities (`generic`), and whether it looks like a recruitment agency posting. In the Streamlit app this costs no extra API call.
2. **Look up the weights.** `cover_letter_weights.txt` is a plain-text table mapping those classifications to shapes and how likely each one is. The first matching row wins. The defaults are starting points, and you can edit them freely:

| Kind of role | Shapes and weights |
|---|---|
| Agency-posted | `direct_short` 60, `three_strengths` 40 |
| Senior, specific JD | `problem_first` 50, `story_first` 40, `question_led` 10 |
| Senior, generic JD | `story_first` 50, `three_strengths` 30, `problem_first` 20 |
| Mid-level, specific JD | `three_strengths` 35, `problem_first` 25, `story_first` 20, `direct_short` 10, `question_led` 10 |
| Mid-level, generic JD | `three_strengths` 50, `direct_short` 30, `story_first` 20 |
| Junior | `three_strengths` 50, `direct_short` 40, `story_first` 10 |

3. **Draw at random.** `shape_selector.py` makes a weighted random choice from the matching row and never repeats the shape used for the previous letter (remembered in a small hidden file next to the outputs, outside the repo; if that file can't be written, letter generation is unaffected).

The randomness lives in the code, not in the prompt: Claude only ever sees the one chosen structure, so it cannot drift back to a default pattern. If the model ever returns a missing or unrecognised classification, neutral defaults are used (senior, generic JD, direct posting).

### Overriding the style

In the Streamlit app, the **Cover letter style** dropdown in the sidebar is set to **Auto** by default. Pick a specific style to force it; this applies to every letter in a batch run too, and Batch Mode shows a warning while a style is forced. The style used is shown under the cover letter, in the batch results, and in the batch summary file.

From the terminal, reading `job_description.txt` and writing to the usual output folder:

```bash
python3 generate_cover_letter.py                 # chosen automatically
python3 generate_cover_letter.py story_first     # force a specific shape
python3 generate_cover_letter.py --list          # show available shapes
```

(On Windows, use `python` instead of `python3`.) The terminal menu and terminal batch mode also select shapes automatically, but they do not yet carry the role classification through, so each letter costs one extra small classification call.

### Adding your own shape

Drop a new `.txt` file into `cover_letter_shapes/`. It becomes available immediately for forcing, with no code change. Follow the format of the existing files: a short header, then paragraph-by-paragraph instructions, referring to the base prompt's FORWARD-LOOKING and CLOSING rules by name rather than restating them. To make it eligible for automatic selection, add it to the relevant rows of `cover_letter_weights.txt`; shapes not listed there are only used when forced.

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

Header/contact lines separated by tab characters in the source document (rather than explicit `|` or `·` separators) are automatically converted to a visible `|` separator during extraction — Word tab characters do not render as spacing when written into a `.docx` TextRun, so this conversion happens in `tailor_cv.py` at read time.

---

## Anti-hallucination and attribution guardrails

The CV tailoring and cover letter prompts explicitly instruct Claude:

- Only surface experience that genuinely exists in the master CV
- Do not fabricate tools, qualifications, or achievements
- Where gaps are structural, leave them as gaps — a lower keyword score is preferable to an inaccurate CV
- Every achievement or metric referenced must be attributed to the exact employer it occurred under — never cross-attributed to a different company, even a similar or adjacent one
- Selection of which achievements to surface may vary by JD, but the substance, numbers, and attribution of each selected achievement must remain unchanged from the master CV
- A small set of specific facts (see Fixed factual rules above) must never drift regardless of how the surrounding text is tailored
- Cover letters favour understatement over self-promotion, and acknowledge prior employment at the same company (where applicable) with humility rather than as a leveraged credential — kept to a brief passing mention where that prior employment is far in the past
- Cover letters avoid repeating the same opening sentence structure, the same "concrete example" transition phrase, or the same closing line across different letters — each letter should read as written for that specific role, not generated from a fixed template
- Cover letters do not mirror the JD's own distinctive phrasing back to the reader (see Echo-prevention above)
- Cover letters describe value to the team as a hypothesis grounded in real experience, never as a promise of results or a claim of insider knowledge about the company (see Cover letter shapes)
- Cover letters name the employer for every achievement they cite, and reproduce metric, tool and product names exactly as written in the master CV
- Cover letters do not unprompted resurface a prior interview or rejection with the same hiring manager if it is not actively remembered — a fresh introduction stays fresh

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

- Apply the tailored tagline and Core Competencies in the Streamlit CV flow — currently only the terminal path (`main()` in `tailor_cv.py`) substitutes them into the CV, while `app.py` builds its CV data from the original header and tables. Planned fix: one shared helper used by both paths
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

### v1.8
- Cover letter restructured into a shared base prompt plus selectable shapes — the fixed four-paragraph structure is replaced by five structures in `cover_letter_shapes/` (`problem_first`, `story_first`, `three_strengths`, `direct_short`, `question_led`), so letters vary in shape and feel and not only in wording
- Cover letters now explicitly cover the writer's strengths, how they fit the role's demands, and the value they could add to the team and organisation, rather than only recounting the past
- Forward-looking rule added — value-to-team passages must be hypotheses grounded in real CV experience, never promises of results or claims of insider knowledge
- Evidence discipline added to cover letters — every achievement must name its own employer (including when several are grouped in one sentence), tool and product names must match the master CV exactly (e.g. "Power BI"), and evidence paragraphs are capped at two or three achievements and must not end on a self-assessment line
- "Memorable without pompous" guidance added — specificity over volume, one point of view, varied rhythm, no superlatives or intensifiers; target length set at 200–280 words
- Cover letter prompt's fixed factual rules now mirror `prompt_config.txt` — Bunker Holding cycle time ("within two quarters"), formal line management only at Infosys, no P&L ownership, on-site vendor engagement in India only with Serbia mentioned only in the 2019 Star Award context, and the lapsed CSM certification never listed
- Automatic, role-weighted shape selection — `extract_job_details()` now also returns `seniority_tier`, `problem_specificity` and `agency_posted` from the same single API call (with safe fallbacks if the model returns anything unexpected); the new `shape_selector.py` reads the editable `cover_letter_weights.txt` and makes a weighted random choice, never repeating the previous letter's shape
- Streamlit: new "Cover letter style" sidebar dropdown (Auto, or force a specific shape, including across a batch run); the style used is shown under the cover letter and in batch results, and recorded in the batch summary file
- `generate_cover_letter()` and `main()` accept optional `shape` and `job_details` parameters; with neither, a shape is chosen automatically from neutral defaults, so existing callers in `menu.py` and `batch_processor.py` keep working unchanged (the terminal flows cost one extra small classification call per letter). A shape can also be forced from the terminal with `python3 generate_cover_letter.py <shape>`
- Fixed `main()` in `generate_cover_letter.py` building its output filename without sanitising `/` in company names (e.g. "Ambu A/S"), which had been fixed elsewhere but missed here
- Cover letter prompt and shape files are now read as UTF-8 and located relative to the module, so they load correctly regardless of working directory or Windows default encoding

### v1.7
- Node.js invocation made cross-platform — replaced hardcoded Mac-only `os.system("cd /Users/... && /usr/local/bin/node ...")` calls with a `run_node_build()` helper in `utils.py` that locates Node via `shutil.which("node")` and invokes it with `subprocess.run(cwd=...)`. No hardcoded paths or shell-specific syntax; works unchanged on macOS, Windows, and (eventually) the Mac Mini as long as Node is on PATH
- Node build failures now surface properly — `run_node_build()` raises with the actual `stderr` on a non-zero exit instead of silently printing, so a failed CV/cover-letter render is never mistaken for a successful one
- Fixed a Windows OneDrive `PermissionError` — `st.download_button` calls in `app.py` were failing intermittently when OneDrive still held a sync lock on a just-written `.docx`. Added a `safe_read_bytes()` helper that briefly retries the read before raising, applied across all 9 download-button call sites (single-JD flow and batch mode, both PASS and BORDERLINE paths)

### v1.6
- Tagline now tailored per JD — the second header line (e.g. "Software Delivery Leadership | Programme & Portfolio Governance | ...") is passed to Claude as a pool of existing pipe-separated phrases; Claude selects and reorders 2-4 of them per role instead of always showing the same fixed line, with no invented phrases allowed
- Core Competencies table now tailored per JD — the full pool of competency rows (previously always shown in full) is passed to the prompt via `format_competencies_for_prompt()`, and Claude selects the 6-8 most relevant, reordered, and reproduced exactly rather than reworded
- Metric-name exactness rule added to ATTRIBUTION INTEGRITY in both `prompt_config.txt` and `cover_letter_prompt.txt` — fixes a real fabrication caught in testing where a cover letter invented "defect escape rates" instead of the master CV's actual "defect slippage"
- Cover letter closing paragraph tightened from "2 sentences" to "EXACTLY 1 sentence," with a named anti-pattern against stacking two eager-sounding sentences (e.g. "I'd be glad to speak further" + "happy to come in whenever works") into one overly keen close
- Stress test residency-duration fix — `stress_test_prompt.txt`'s CANDIDATE PROFILE now explicitly states continuous Denmark residence since 2018 (8+ years), with an explicit instruction not to infer recent country-of-origin residence from the candidate's Bachelor's degree location. Fixes a false FAIL on a security-clearance residency requirement that was incorrectly triggered by degree-country inference

### v1.5
- Stress test expanded from 11 to 12 parameters — added Role-Type Fit, which flags pure-strategy, L&D, and standalone process-excellence individual-contributor roles outside the candidate's actual delivery-focused target
- Location parameter widened — bus added as a valid commute mode alongside train/metro, more commuter towns explicitly listed as in-range, more distant cities explicitly listed as out-of-range
- Salary parameter clarified as base salary only, excluding pension and bonus
- Candidate profile expanded with permanent residency timeline, explicit language proficiency detail, and an explicit statement of target role types (delivery and delivery-adjacent only)
- Echo-prevention rule added to both the CV tailoring and cover letter prompts — Claude no longer mirrors the JD's own distinctive phrasing back to the reader in either the summary or the letter, reducing the "parroting the posting" tell
- Fixed Factual Rules block added to both prompts — a small set of specific, non-negotiable facts (exact tenure dates, precise seniority wording, named vendors only, specific metric phrasing, explicit exclusions) that must never drift regardless of how the surrounding text is tailored
- Prior-contact rule added to the cover letter prompt — a previous interview or rejection with the same hiring manager is not unprompted resurfaced if it is not actively remembered
- Cover letter now aware of closely-associated Danish employer groupings (e.g. APM Terminals and A.P. Møller–Mærsk) to avoid treating related companies as unrelated
- Humility guidance refined — prior employment at the same company gets only a brief passing mention when that history is far in the past, rather than being developed further
- Collinson Group exception added to achievement selection — this pre-2015 role may surface as its own entry (bypassing standard Earlier Career consolidation) when a JD is genuinely centred on agile practice or delivery enablement
- Fixed header/contact line extraction — tab-separated content in the master CV (phone / email / LinkedIn) is now converted to a visible `|` separator during extraction, since raw tab characters do not render as spacing inside a generated `.docx`

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

## Running on another machine (Mac mini, Windows laptop, etc.)

The app itself is plain Python (Streamlit) + two Node.js scripts for `.docx` generation, invoked via `run_node_build()` in `utils.py` (see the v1.7 changelog entry above) — no hardcoded paths or shell-specific syntax, so the same repo runs on macOS, Windows, or Linux as long as Python and Node are installed. To run it on a new machine:

1. **Clone the repo** from GitHub (subh-c-ydv/cv-tailor).
2. **Install Python deps:**
   ```bash
   pip3 install anthropic python-docx streamlit
   ```
3. **Install Node.js** (any recent LTS) and make sure `node` is on your PATH — `run_node_build()` finds it via `shutil.which("node")`, so no manual path configuration is needed.
   ```bash
   cd cv-tailor
   npm install docx
   ```
4. **Set your API key** as an environment variable named `ANTHROPIC_API_KEY` — there's no `.env` file in this codebase; `utils.py` reads it straight from `os.environ`.
   - macOS/Linux: add `export ANTHROPIC_API_KEY="your-key-here"` to `~/.zshrc` (or `~/.bashrc`) and `source` it
   - Windows: set it as a User Environment Variable via System Properties, or `$env:ANTHROPIC_API_KEY="your-key-here"` in your PowerShell profile
5. **Create `cv-inputs/` and `cv-outputs/`** one level above the repo folder (see `config.py` for the exact paths it expects) — copy over `master_cv.docx` and `job_description.txt` from your current machine.
6. **Run it:**
   ```bash
   streamlit run app.py
   ```
   Then open http://localhost:8501. On macOS this can also run as a persistent background service (see "Running as a persistent background service (macOS)" above) — there's currently no Windows equivalent, so on Windows you start it manually each session.