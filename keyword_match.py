import os

from utils import read_jd, read_cv_text, get_client, load_prompt, ask_claude_json


def _clean_keyword_list(value):
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def normalise_keyword_report(raw):
    """Validate the model's keyword match JSON. The score drives the gates, so
    it must be a number: "7", 7.0 and "7/10" are accepted and clamped to 0-10;
    anything else is an error rather than a silent guess."""
    score_text = str(raw.get("score", "")).split("/")[0].strip()
    try:
        score = int(round(float(score_text)))
    except ValueError:
        raise ValueError(f"Keyword match returned no usable score: {raw.get('score')!r}")

    return {
        "score": max(0, min(10, score)),
        "matching_keywords": _clean_keyword_list(raw.get("matching_keywords")),
        "missing_keywords": _clean_keyword_list(raw.get("missing_keywords")),
        "gaps": str(raw.get("gaps") or ""),
        "recommendation": str(raw.get("recommendation") or ""),
    }


def run_keyword_match(jd_text, cv_text, client):
    prompt = load_prompt("keyword_match_prompt.txt").format(
        jd_text=jd_text,
        cv_text=cv_text
    )
    raw = ask_claude_json(client, prompt, max_tokens=2000, what="keyword match")
    return normalise_keyword_report(raw)


def print_keyword_report(report):
    score = report["score"]

    print("\n" + "=" * 50)
    print("   KEYWORD MATCH REPORT")
    print("=" * 50)

    print(f"\n  Score: {score}/10")

    if score >= 7:
        print("  ✅  Strong match")
    elif score >= 4:
        print("  ⚠️   Moderate match")
    else:
        print("  ❌  Weak match")

    print(f"\n  Matching keywords:")
    for kw in report["matching_keywords"]:
        print(f"    ✅  {kw}")

    print(f"\n  Missing keywords:")
    for kw in report["missing_keywords"]:
        print(f"    ❌  {kw}")

    print(f"\n  Gaps: {report['gaps']}")
    print(f"\n  Recommendation: {report['recommendation']}")
    print("=" * 50)


def save_keyword_report(report, output_dir):
    score = report["score"]
    lines = [
        "KEYWORD MATCH REPORT",
        "=" * 40,
        f"Score: {score}/10",
        "",
        "Matching Keywords:",
    ]
    for kw in report["matching_keywords"]:
        lines.append(f"  + {kw}")

    lines += ["", "Missing Keywords:"]
    for kw in report["missing_keywords"]:
        lines.append(f"  - {kw}")

    lines += [
        "",
        f"Gaps: {report['gaps']}",
        "",
        f"Recommendation: {report['recommendation']}"
    ]

    path = os.path.join(output_dir, "keyword_match_report.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write('\n'.join(lines))

    print(f"\n  Report saved to: {path}")


def main():
    print("\nReading job description and CV...")
    jd_text = read_jd()
    cv_text = read_cv_text()

    client = get_client()

    print("Running keyword match...")
    report = run_keyword_match(jd_text, cv_text, client)
    print_keyword_report(report)

    return report


if __name__ == "__main__":
    main()
