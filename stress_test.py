import anthropic
import os
import json
from utils import read_jd


def run_stress_test(jd_text, client):
    with open("stress_test_prompt.txt", "r") as f:
        prompt_template = f.read()

    prompt = prompt_template.format(jd_text=jd_text)

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


def print_stress_test_report(report):
    overall = report["overall"]

    print("\n" + "=" * 50)
    print("   STRESS TEST REPORT")
    print("=" * 50)

    for param in report["parameters"]:
        result = param["result"]
        if result == "PASS":
            icon = "✅"
        elif result == "FAIL":
            icon = "❌"
        else:
            icon = "⚠️ "
        print(f"\n{icon}  {param['name']}: {result}")
        print(f"    {param['reason']}")

    print("\n" + "-" * 50)

    if overall == "PASS":
        print("✅  OVERALL: PASS")
    elif overall == "FAIL":
        print("❌  OVERALL: FAIL")
    else:
        print("⚠️   OVERALL: BORDERLINE")

    print(f"\n    {report['verdict']}")
    print("=" * 50)


def main():
    print("\nReading job description...")
    jd_text = read_jd()

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    print("Running stress test...")
    report = run_stress_test(jd_text, client)
    print_stress_test_report(report)

    return report


if __name__ == "__main__":
    main()