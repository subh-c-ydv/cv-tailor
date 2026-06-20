import os
import anthropic
from datetime import datetime
from config import OUTPUTS_DIR
from utils import extract_job_details


def get_jd_files():
    """Scan cv-inputs/jds/ for all .txt files"""
    jds_folder = os.path.join(os.path.dirname(__file__), "..", "cv-inputs", "jds")
    os.makedirs(jds_folder, exist_ok=True)

    files = [f for f in os.listdir(jds_folder) if f.endswith(".txt")]
    return jds_folder, sorted(files)


def read_jd_file(jds_folder, filename):
    with open(os.path.join(jds_folder, filename), "r") as f:
        return f.read()


def process_single_jd(jd_text, cv_text, client):
    """Run full pipeline for a single JD — returns result dict"""
    from stress_test import run_stress_test, print_stress_test_report
    from keyword_match import run_keyword_match, print_keyword_report, save_keyword_report
    from tailor_cv import main as tailor_main
    from generate_cover_letter import main as cover_main

    result = {
        "job_title": "Unknown",
        "company_name": "Unknown",
        "stress_test": None,
        "keyword_score": None,
        "status": None,
        "stop_reason": None,
        "output_dir": None,
        "jd_text": jd_text
    }

    # Gate 1 — Stress Test
    print("\n--- Gate 1: Stress Test ---")
    stress_report = run_stress_test(jd_text, client)
    print_stress_test_report(stress_report)
    result["stress_test"] = stress_report["overall"]

    if stress_report["overall"] == "FAIL":
        result["status"] = "FAIL"
        result["stop_reason"] = f"Failed stress test — {stress_report['verdict']}"
        return result

    if stress_report["overall"] == "BORDERLINE":
        result["status"] = "BORDERLINE"
        result["stop_reason"] = f"Borderline stress test — {stress_report['verdict']}"
        return result

    # Gate 2 — Keyword Match
    print("\n--- Gate 2: Keyword Match ---")
    keyword_report = run_keyword_match(jd_text, cv_text, client)
    print_keyword_report(keyword_report)

    score = keyword_report["score"]
    missing_keywords = keyword_report.get("missing_keywords", [])
    gaps = keyword_report.get("gaps", "")
    result["keyword_score"] = score
    result["missing_keywords"] = missing_keywords
    result["gaps"] = gaps

    if score <= 3:
        result["status"] = "FAIL"
        result["stop_reason"] = f"Keyword match too low ({score}/10)"
        return result

    if score <= 6:
        result["status"] = "BORDERLINE"
        result["stop_reason"] = f"Moderate keyword match ({score}/10) — review recommended"
        return result

    # Both gates cleared — extract job details
    job_details = extract_job_details(jd_text, client)
    job_title = job_details["job_title"]
    company_name = job_details["company_name"]
    result["job_title"] = job_title
    result["company_name"] = company_name
    print(f"\n  → {job_title} at {company_name}")

    folder_name = f"{job_title} @ {company_name}".replace("/", "-")
    output_dir = os.path.join(OUTPUTS_DIR, folder_name)
    os.makedirs(output_dir, exist_ok=True)
    result["output_dir"] = output_dir

    save_keyword_report(keyword_report, output_dir)

    print("\n--- Building CV ---")
    tailor_main(
        job_title=job_title,
        company_name=company_name,
        output_dir=output_dir,
        missing_keywords=missing_keywords,
        gaps=gaps
    )

    print("\n--- Generating Cover Letter ---")
    cover_main(
        job_title=job_title,
        company_name=company_name,
        output_dir=output_dir,
        missing_keywords=missing_keywords,
        gaps=gaps,
        jd_text=jd_text
    )

    result["status"] = "PASS"
    return result


def process_borderline_interactively(borderline_results, cv_text, client):
    """Offer to process borderline roles interactively after batch run"""
    from stress_test import run_stress_test, print_stress_test_report
    from keyword_match import run_keyword_match, print_keyword_report, save_keyword_report
    from tailor_cv import main as tailor_main
    from generate_cover_letter import main as cover_main

    print("\n" + "=" * 50)
    print("   BORDERLINE ROLES")
    print("=" * 50)
    print("\nThe following roles were flagged as borderline:\n")

    for i, r in enumerate(borderline_results, 1):
        label = f"{r['job_title']} @ {r['company_name']}"
        print(f"  {i}. {label}")
        print(f"     {r['stop_reason']}")

    print()
    choice = input("Would you like to process any of these now? (y/n): ").strip().lower()

    if choice != "y":
        print("\nSkipping borderline roles.")
        return

    print("\nEnter the number(s) of the roles you want to process.")
    print("Separate multiple numbers with commas (e.g. 1,3):")
    selection = input("> ").strip()

    try:
        indices = [int(x.strip()) - 1 for x in selection.split(",")]
    except ValueError:
        print("\nInvalid selection. Skipping.")
        return

    for idx in indices:
        if idx < 0 or idx >= len(borderline_results):
            print(f"\n  Invalid selection: {idx + 1}. Skipping.")
            continue

        r = borderline_results[idx]
        jd_text = r["jd_text"]
        label = f"{r['job_title']} @ {r['company_name']}"

        print(f"\n{'=' * 50}")
        print(f"  Processing borderline: {label}")
        print("=" * 50)

        print(f"\n  Stop reason: {r['stop_reason']}")
        proceed = input("\n  Proceed and generate CV + Cover Letter? (y/n): ").strip().lower()

        if proceed != "y":
            print(f"\n  Skipping {label}.")
            continue

        # Extract job details if not already known
        job_title = r["job_title"]
        company_name = r["company_name"]

        if job_title == "Unknown":
            job_details = extract_job_details(jd_text, client)
            job_title = job_details["job_title"]
            company_name = job_details["company_name"]

        print(f"  → {job_title} at {company_name}")

        folder_name = f"{job_title} @ {company_name}".replace("/", "-")
        output_dir = os.path.join(OUTPUTS_DIR, folder_name)
        os.makedirs(output_dir, exist_ok=True)

        # Run keyword match if not already done
        missing_keywords = r.get("missing_keywords", [])
        gaps = r.get("gaps", "")

        if not missing_keywords and not gaps:
            print("\n--- Running Keyword Match ---")
            keyword_report = run_keyword_match(jd_text, cv_text, client)
            print_keyword_report(keyword_report)
            save_keyword_report(keyword_report, output_dir)
            missing_keywords = keyword_report.get("missing_keywords", [])
            gaps = keyword_report.get("gaps", "")

        print("\n--- Building CV ---")
        tailor_main(
            job_title=job_title,
            company_name=company_name,
            output_dir=output_dir,
            missing_keywords=missing_keywords,
            gaps=gaps
        )

        print("\n--- Generating Cover Letter ---")
        cover_main(
            job_title=job_title,
            company_name=company_name,
            output_dir=output_dir,
            missing_keywords=missing_keywords,
            gaps=gaps,
            jd_text=jd_text
        )

        print(f"\n✅  Files saved to: {output_dir}")


def print_batch_summary(results):
    """Print batch summary to terminal"""
    print("\n" + "=" * 50)
    print("   BATCH SUMMARY")
    print("=" * 50)

    for r in results:
        label = f"{r['job_title']} @ {r['company_name']}"
        score = f"  (keyword: {r['keyword_score']}/10)" if r['keyword_score'] else ""

        if r["status"] == "PASS":
            print(f"\n✅  PASS       {label}{score}")
        elif r["status"] == "FAIL":
            print(f"\n❌  FAIL       {label}")
            print(f"    Reason: {r['stop_reason']}")
        else:
            print(f"\n⚠️   BORDERLINE  {label}{score}")
            print(f"    Note: {r['stop_reason']}")

    print("\n" + "-" * 50)
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    borderline = sum(1 for r in results if r["status"] == "BORDERLINE")

    print(f"\n  {total} jobs processed.")
    print(f"  ✅  {passed} passed")
    print(f"  ❌  {failed} failed")
    print(f"  ⚠️   {borderline} borderline")
    print("=" * 50)


def save_batch_summary(results):
    """Save batch summary to cv-outputs/ with timestamp"""
    timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M")
    filename = f"batch_summary_{timestamp}.txt"
    filepath = os.path.join(OUTPUTS_DIR, filename)

    lines = [
        "BATCH SUMMARY",
        f"Run: {datetime.now().strftime('%d %B %Y, %H:%M')}",
        "=" * 40,
        ""
    ]

    for r in results:
        label = f"{r['job_title']} @ {r['company_name']}"
        score = f"  (keyword: {r['keyword_score']}/10)" if r['keyword_score'] else ""

        if r["status"] == "PASS":
            lines.append(f"PASS       {label}{score}")
        elif r["status"] == "FAIL":
            lines.append(f"FAIL       {label}")
            lines.append(f"  Reason: {r['stop_reason']}")
        else:
            lines.append(f"BORDERLINE {label}{score}")
            lines.append(f"  Note: {r['stop_reason']}")
        lines.append("")

    lines += [
        "-" * 40,
        f"Total: {len(results)} jobs processed",
        f"Passed: {sum(1 for r in results if r['status'] == 'PASS')}",
        f"Failed: {sum(1 for r in results if r['status'] == 'FAIL')}",
        f"Borderline: {sum(1 for r in results if r['status'] == 'BORDERLINE')}",
    ]

    with open(filepath, "w") as f:
        f.write('\n'.join(lines))

    print(f"\n  Batch summary saved to: {filepath}")


def run_batch():
    """Main batch processing function"""
    from utils import read_cv_text

    jds_folder, jd_files = get_jd_files()

    if not jd_files:
        print(f"\n  No JD files found in cv-inputs/jds/")
        print(f"  Add .txt files there and try again.")
        return

    print(f"\n  Found {len(jd_files)} JD(s) to process:")
    for f in jd_files:
        print(f"    • {f}")

    print("\n" + "=" * 50)

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    cv_text = read_cv_text()

    results = []

    for i, filename in enumerate(jd_files, 1):
        print(f"\n{'=' * 50}")
        print(f"  Processing {i}/{len(jd_files)}: {filename}")
        print("=" * 50)

        jd_text = read_jd_file(jds_folder, filename)

        try:
            result = process_single_jd(jd_text, cv_text, client)

            if result["job_title"] == "Unknown":
                try:
                    job_details = extract_job_details(jd_text, client)
                    result["job_title"] = job_details["job_title"]
                    result["company_name"] = job_details["company_name"]
                except Exception:
                    result["job_title"] = filename.replace(".txt", "")
                    result["company_name"] = "Unknown"

            results.append(result)

        except Exception as e:
            print(f"\n  ⚠️  Error processing {filename}: {e}")
            results.append({
                "job_title": filename.replace(".txt", ""),
                "company_name": "Unknown",
                "stress_test": None,
                "keyword_score": None,
                "status": "FAIL",
                "stop_reason": f"Processing error: {str(e)}",
                "output_dir": None,
                "jd_text": jd_text
            })

    # Print and save batch summary
    print_batch_summary(results)
    save_batch_summary(results)

    # Offer to process borderline roles interactively
    borderline_results = [r for r in results if r["status"] == "BORDERLINE"]
    print(f"\n  Debug: {len(borderline_results)} borderline result(s) found.")

    if borderline_results:
        process_borderline_interactively(borderline_results, cv_text, client)
    else:
        print("\n  No borderline roles to process.")