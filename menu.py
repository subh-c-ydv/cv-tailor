import os
import anthropic
from utils import read_jd, read_cv_text, extract_job_details
from config import OUTPUTS_DIR


def print_header():
    print("\n" + "=" * 50)
    print("   CV TAILOR — Subhash Chandra Yadav")
    print("=" * 50)


def print_menu():
    print("\nWhat would you like to do?\n")
    print("  1. Stress Test only")
    print("  2. Keyword Match only")
    print("  3. Full Run (Stress Test → Keyword Match → CV + Cover Letter)")
    print("  4. Tailor CV only")
    print("  5. Generate Cover Letter only")
    print("  6. Both CV + Cover Letter")
    print("  7. Exit")
    print()


def ask_proceed(label):
    print(f"\n⚠️   {label}")
    choice = input("  Proceed anyway? (y/n): ").strip().lower()
    return choice == "y"


def run_full_pipeline(jd_text, cv_text, client):
    from stress_test import run_stress_test, print_stress_test_report
    from keyword_match import run_keyword_match, print_keyword_report, save_keyword_report
    from tailor_cv import main as tailor_main
    from generate_cover_letter import main as cover_main

    # Gate 1 — Stress Test
    print("\n--- Gate 1: Stress Test ---")
    stress_report = run_stress_test(jd_text, client)
    print_stress_test_report(stress_report)

    overall = stress_report["overall"]

    if overall == "FAIL":
        print("\n❌  Role failed stress test. Stopping here.")
        return

    if overall == "BORDERLINE":
        if not ask_proceed("Stress test is BORDERLINE."):
            print("\nStopped at stress test.")
            return

    # Gate 2 — Keyword Match
    print("\n--- Gate 2: Keyword Match ---")
    keyword_report = run_keyword_match(jd_text, cv_text, client)
    print_keyword_report(keyword_report)

    score = keyword_report["score"]
    missing_keywords = keyword_report.get("missing_keywords", [])
    gaps = keyword_report.get("gaps", "")

    if score <= 3:
        if not ask_proceed(f"Keyword match score is low ({score}/10). This role may not be a strong fit."):
            print("\nStopped at keyword match.")
            return

    elif score <= 6:
        if not ask_proceed(f"Keyword match score is moderate ({score}/10). Some gaps exist."):
            print("\nStopped at keyword match.")
            return

    # Both gates cleared
    print("\n✅  Both gates cleared. Proceeding to build documents...")
    job_details = extract_job_details(jd_text, client)
    job_title = job_details["job_title"]
    company_name = job_details["company_name"]
    print(f"  → {job_title} at {company_name}")

    folder_name = f"{job_title} @ {company_name}".replace("/", "-")
    output_dir = os.path.join(OUTPUTS_DIR, folder_name)
    os.makedirs(output_dir, exist_ok=True)

    # Save keyword report
    save_keyword_report(keyword_report, output_dir)

    # Build CV — pass keyword gaps
    print("\n--- Building CV ---")
    job_title, company_name, output_dir = tailor_main(
        job_title=job_title,
        company_name=company_name,
        output_dir=output_dir,
        missing_keywords=missing_keywords,
        gaps=gaps
    )

    # Build cover letter — pass keyword gaps
    print("\n--- Generating Cover Letter ---")
    cover_main(
        job_title=job_title,
        company_name=company_name,
        output_dir=output_dir,
        missing_keywords=missing_keywords,
        gaps=gaps
    )

    print(f"\n✅  All files saved to: {output_dir}")


def main():
    print_header()

    while True:
        print_menu()
        choice = input("Enter your choice (1-7): ").strip()

        if choice == "1":
            print("\n--- Stress Test ---")
            from stress_test import main as stress_main
            stress_main()

        elif choice == "2":
            print("\n--- Keyword Match ---")
            from keyword_match import main as keyword_main
            keyword_main()

        elif choice == "3":
            print("\n--- Full Run ---")
            jd_text = read_jd()
            cv_text = read_cv_text()
            client = anthropic.Anthropic(
                api_key=os.environ.get("ANTHROPIC_API_KEY")
            )
            run_full_pipeline(jd_text, cv_text, client)

        elif choice == "4":
            print("\n--- Tailoring CV ---")
            from tailor_cv import main as tailor_main
            tailor_main()

        elif choice == "5":
            print("\n--- Generating Cover Letter ---")
            from generate_cover_letter import main as cover_main
            cover_main()

        elif choice == "6":
            print("\n--- CV + Cover Letter ---")
            from tailor_cv import main as tailor_main
            from generate_cover_letter import main as cover_main
            job_title, company_name, output_dir = tailor_main()
            cover_main(
                job_title=job_title,
                company_name=company_name,
                output_dir=output_dir
            )
            print(f"\n✅  All files saved to: {output_dir}")

        elif choice == "7":
            print("\nGood luck with the applications, Subhash. Closing.\n")
            break

        else:
            print("\n  Please enter 1 through 7.")

        print("\n" + "-" * 50)
        input("Press Enter to return to the menu...")


if __name__ == "__main__":
    main()