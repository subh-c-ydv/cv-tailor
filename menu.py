import os
import subprocess


def print_header():
    print("\n" + "=" * 50)
    print("   CV TAILOR — Subhash Chandra Yadav")
    print("=" * 50)


def print_menu():
    print("\nWhat would you like to do?\n")
    print("  1. Tailor CV")
    print("  2. Generate Cover Letter")
    print("  3. Both")
    print("  4. Exit")
    print()


def run_script(script_name):
    result = subprocess.run(["python3", script_name])
    if result.returncode != 0:
        print(f"\n⚠️  Something went wrong running {script_name}.")


def main():
    print_header()

    while True:
        print_menu()
        choice = input("Enter your choice (1-4): ").strip()

        if choice == "1":
            print("\n--- Tailoring CV ---")
            run_script("tailor_cv.py")

        elif choice == "2":
            print("\n--- Generating Cover Letter ---")
            run_script("generate_cover_letter.py")

        elif choice == "3":
            print("\n--- Tailoring CV ---")
            run_script("tailor_cv.py")
            print("\n--- Generating Cover Letter ---")
            run_script("generate_cover_letter.py")

        elif choice == "4":
            print("\nGood luck with the applications, Subhash. Closing.\n")
            break

        else:
            print("\n  Please enter 1, 2, 3 or 4.")

        print("\n" + "-" * 50)
        input("Press Enter to return to the menu...")


if __name__ == "__main__":
    main()