from utils import load_prompt, ask_claude_json

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
