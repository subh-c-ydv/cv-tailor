import anthropic
import os
import json
from utils import read_jd, read_cv_text


def run_keyword_match(jd_text, cv_text, client):
    with open("keyword_match_prompt.txt", "r") as f:
        prompt_template = f.read()

    prompt = prompt_template.format(
        jd_text=jd_text,
        cv_text=cv_text
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = message.content[0].text.strip()
    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]

    return json.loads(response_text.strip())


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
    with open(path, "w") as f:
        f.write('\n'.join(lines))

    print(f"\n  Report saved to: {path}")


def main():
    print("\nReading job description and CV...")
    jd_text = read_jd()
    cv_text = read_cv_text()

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    print("Running keyword match...")
    report = run_keyword_match(jd_text, cv_text, client)
    print_keyword_report(report)

    return report


if __name__ == "__main__":
    main()