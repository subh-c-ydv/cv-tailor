"""Deterministic checks of generated CVs and cover letters against the
FIXED FACTUAL RULES in prompt_config.txt and cover_letter_prompt.txt.

The prompts ask Claude to follow these rules; this module verifies that it
did. It uses no LLM, so it is free, fast and repeatable.

Two severities:
  violation - almost certainly breaks a rule; fix before sending
  review    - may break a rule depending on context; read the sentence

Usage:
  python fact_check.py                 # scan every .docx under cv-outputs/
  python fact_check.py path/to/a.docx  # scan specific files or folders
Exit code is 1 if any violation is found, so it can gate a script.
"""
import os
import re
import sys
from dataclasses import dataclass

VIOLATION = "violation"
REVIEW = "review"


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    message: str
    excerpt: str


@dataclass(frozen=True)
class PatternRule:
    rule: str
    severity: str
    pattern: re.Pattern
    message: str


def _rx(pattern, flags=re.IGNORECASE):
    return re.compile(pattern, flags)


PATTERN_RULES = [
    PatternRule("cio_level", VIOLATION, _rx(r"\bCIO[\s-]level\b"),
                'Use "CIO-1 level", never "CIO level".'),
    PatternRule("transferable_permit", VIOLATION, _rx(r"\(transferable\)"),
                'Work permit is "employer-sponsored" — never add "(transferable)".'),
    PatternRule("wrong_vendor", VIOLATION, _rx(r"\b(IBM|Endava)\b"),
                "TCS and Ubique Systems are the only vendors that may be named."),
    PatternRule("portfolio_name", VIOLATION, _rx(r"\bCP&S\b|Customer Products (&|and) Services"),
                'Use "Digital Products Portfolio (DPP)", never "CP&S".'),
    PatternRule("apmt_tenure", VIOLATION,
                _rx(r"\b(seven|7)[\s-]+years?\b[^.]{0,80}\bAPM Terminals\b"
                    r"|\bAPM Terminals\b[^.]{0,80}\b(seven|7)[\s-]+years?\b"),
                "APM Terminals tenure is three years (2022-2025), never seven."),
    PatternRule("pnl_ownership", VIOLATION,
                _rx(r"\b(own|owned|owner|ownership|accountab\w*|responsib\w*)\b[^.]{0,40}\bP&L\b"
                    r"|\bP&L\b[^.]{0,20}\b(owner|ownership|accountab\w*|responsib\w*)\b"),
                "Never claim P&L ownership; describe trusted stewardship / full visibility of spend."),
    PatternRule("pnl_mention", REVIEW, _rx(r"\bP&L\b"),
                "P&L is mentioned; make sure it doesn't imply ownership."),
    PatternRule("csm_certification", VIOLATION, _rx(r"\bCSM\b|Certified Scrum\s?Master"),
                "The lapsed CSM certification must never be mentioned."),
    PatternRule("defect_metric_name", VIOLATION, _rx(r"\bdefect escape"),
                'The metric is "defect slippage"; don\'t rename it.'),
    PatternRule("tool_name", VIOLATION, _rx(r"\bPowerBI\b|\bADO\b", 0),
                'Write tool names exactly: "Power BI", "Azure DevOps".'),
    # (?<![-\w]) skips compounds such as "compliance-led".
    PatternRule("led_payments", REVIEW, _rx(r"(?<![-\w])led\b[^.]{0,60}\bpayments?\b"),
                'Payments digitalisation work is "facilitated delivery of", never "led".'),
    PatternRule("us_spelling", REVIEW, _rx(r"\bprograms?\b"),
                'UK English: "programme", not "program" (fine inside a quoted job title).'),
    PatternRule("template_leftover", VIOLATION,
                _rx(r"\{[a-z_]+\}|\[(company|hiring manager|name|role|job title)[^\]]*\]"),
                "An unfilled template placeholder was left in the text."),
]

_SIGN_OFF = _rx(r"\b(kind regards|best regards|warm regards|yours sincerely|yours faithfully)\b")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def _excerpt(text, start, end, width=60):
    a = max(0, start - width)
    b = min(len(text), end + width)
    snippet = text[a:b].replace("\n", " ").strip()
    return ("…" if a > 0 else "") + snippet + ("…" if b < len(text) else "")


def _sentences(text):
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def _check_sentence_rules(text):
    """Rules that depend on what else appears in the same sentence."""
    findings = []
    for sentence in _sentences(text):
        lower = sentence.lower()

        # Bunker Holding cycle time: above 20 days -> below 14 days, within two quarters.
        if "cycle time" in lower and ("bunker" in lower or "days" in lower):
            days = {int(n) for n in re.findall(r"\b(\d+)\s*(?:-\s*)?days?\b", lower)}
            wrong_days = days - {14, 20}
            faster = re.search(r"\b(one|a single|1)\s+quarter\b|\b\d+\s+(weeks?|months?)\b", lower)
            if wrong_days or faster:
                findings.append(Finding(
                    "bunker_cycle_time", VIOLATION,
                    'Bunker cycle time is "above 20 days to below 14 days within two quarters".',
                    sentence))

        # Line management applies only to Infosys. In the CV the employer is
        # on the job header line, so the Infosys bullet is recognised by its
        # team size (30) rather than by the company name.
        infosys_context = "infosys" in lower or re.search(r"\bteam of 30\b|\b30-person\b", lower)
        if re.search(r"\bline[- ]manag\w*|\bdirect reports?\b|\bmanaged a team\b", lower) and not infosys_context:
            findings.append(Finding(
                "line_management", REVIEW,
                "Formal line management was only at Infosys (team of 30); Denmark roles were coaching through influence.",
                sentence))

        # Serbia only in the 2019 Maersk Star Award context.
        if "serbia" in lower and "2019" not in lower and "star award" not in lower:
            findings.append(Finding(
                "serbia_context", REVIEW,
                "Serbia may only be mentioned with the 2019 Maersk Star Award.",
                sentence))
    return findings


def _remove_allowed(text, allowed_phrases):
    """Blank out phrases that legitimately break a rule, e.g. a JD's own job
    title such as "Program Manager", so they don't produce false findings."""
    for phrase in allowed_phrases:
        if phrase and phrase.strip():
            text = re.sub(re.escape(phrase.strip()), " ", text, flags=re.IGNORECASE)
    return text


def check_text(text, allowed_phrases=()):
    """Check one document's text. Returns a list of Findings, violations first."""
    text = _remove_allowed(text or "", allowed_phrases)
    findings = []

    for rule in PATTERN_RULES:
        for match in rule.pattern.finditer(text):
            findings.append(Finding(rule.rule, rule.severity, rule.message,
                                    _excerpt(text, match.start(), match.end())))

    # A P&L ownership violation already covers the softer "mention" finding.
    if any(f.rule == "pnl_ownership" for f in findings):
        findings = [f for f in findings if f.rule != "pnl_mention"]

    markers = list(re.finditer(r"\*\*", text))
    if markers:
        findings.append(Finding(
            "markdown_leftover", VIOLATION,
            f"{len(markers)} markdown bold marker(s) (**) are printed literally instead of rendered as bold.",
            _excerpt(text, markers[0].start(), markers[0].end())))

    sign_offs = list(_SIGN_OFF.finditer(text))
    if len(sign_offs) > 1:
        findings.append(Finding(
            "duplicate_sign_off", VIOLATION,
            "The letter closes twice (the document already adds 'Kind regards,').",
            _excerpt(text, sign_offs[0].start(), sign_offs[0].end())))

    findings.extend(_check_sentence_rules(text))
    findings.sort(key=lambda f: f.severity != VIOLATION)
    return findings


def docx_text(path):
    from docx import Document
    doc = Document(path)
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(parts)


def allowed_phrases_for(path):
    """Output folders are named '<job title> @ <company>'; the title and
    company may legitimately contain words the rules would flag."""
    folder = os.path.basename(os.path.dirname(os.path.abspath(path)))
    return [part.strip() for part in folder.split(" @ ")] if " @ " in folder else []


def check_docx(path, allowed_phrases=None):
    if allowed_phrases is None:
        allowed_phrases = allowed_phrases_for(path)
    return check_text(docx_text(path), allowed_phrases)


def _iter_docx(paths):
    for path in paths:
        if os.path.isdir(path):
            for root, _dirs, files in os.walk(path):
                for name in sorted(files):
                    if name.lower().endswith(".docx") and not name.startswith("~$"):
                        yield os.path.join(root, name)
        elif path.lower().endswith(".docx"):
            yield path


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        from config import OUTPUTS_DIR
        argv = [OUTPUTS_DIR]

    files = violations = reviews = 0
    for path in _iter_docx(argv):
        files += 1
        try:
            findings = check_docx(path)
        except Exception as e:  # unreadable or locked file
            print(f"\n{path}\n  ⚠️  could not read: {e}")
            continue
        if not findings:
            continue
        print(f"\n{path}")
        for f in findings:
            marker = "❌" if f.severity == VIOLATION else "⚠️ "
            print(f"  {marker} [{f.rule}] {f.message}\n      “{f.excerpt}”")
        violations += sum(f.severity == VIOLATION for f in findings)
        reviews += sum(f.severity == REVIEW for f in findings)

    print(f"\nChecked {files} document(s): {violations} violation(s), {reviews} to review.")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
