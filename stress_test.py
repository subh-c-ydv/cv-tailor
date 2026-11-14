from utils import read_jd, get_client, load_prompt, ask_claude_json

OVERALL_RESULTS = ("PASS", "FAIL", "BORDERLINE")
PARAMETER_RESULTS = ("PASS", "FAIL", "FLAG", "BORDERLINE")


def _clean_result(value, allowed, default):
    value = str(value or "").strip().upper()
    return value if value in allowed else default


def normalise_stress_report(raw):
    """Validate the model's stress test JSON so a missing or unexpected field
    can never crash the pipeline. An unrecognised overall result is treated as
    BORDERLINE, so a human decides rather than the app silently passing it."""
    parameters = raw.get("parameters")
    if not isinstance(parameters, list):
        parameters = []

    clean_parameters = [
        {
            "name": str(p.get("name") or "Unnamed check"),
            "result": _clean_result(p.get("result"), PARAMETER_RESULTS, "FLAG"),
            "reason": str(p.get("reason") or ""),
        }
        for p in parameters
        if isinstance(p, dict)
    ]

    return {
        "overall": _clean_result(raw.get("overall"), OVERALL_RESULTS, "BORDERLINE"),
        "verdict": str(raw.get("verdict") or "No verdict given."),
        "parameters": clean_parameters,
    }


def run_stress_test(jd_text, client):
    prompt = load_prompt("stress_test_prompt.txt").format(jd_text=jd_text)
    raw = ask_claude_json(client, prompt, max_tokens=2000, what="stress test")
    return normalise_stress_report(raw)


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

    client = get_client()

    print("Running stress test...")
    report = run_stress_test(jd_text, client)
    print_stress_test_report(report)

    return report


if __name__ == "__main__":
    main()
