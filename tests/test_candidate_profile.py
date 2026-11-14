"""Personal details live in cv-inputs/profile.toml, outside the repository.
These tests check the profile is loaded and used, and guard against personal
details creeping back into the (public) repository."""
import os
import re
import subprocess

import pytest

import candidate_profile
import config
import generate_cover_letter
import stress_test
import utils
from conftest import REPO_ROOT


# --- Loading --------------------------------------------------------------------------

def test_test_profile_is_loaded():
    profile = candidate_profile.load_profile()
    assert profile["name"] == "Jane Example"
    assert profile["filename_prefix"] == "Jane_Example"
    assert profile["candidate_profile"] == "- TEST PROFILE LINE: based in Testby"


def test_example_file_in_repo_is_valid():
    profile = candidate_profile.load_profile(os.path.join(REPO_ROOT, "profile.example.toml"))
    assert profile["name"] == "Jane Example"
    assert profile["candidate_profile"].startswith("- Based in")


def test_missing_profile_explains_what_to_do(tmp_path):
    with pytest.raises(candidate_profile.ProfileError, match="profile.example.toml"):
        candidate_profile.load_profile(str(tmp_path / "nope.toml"))


def test_missing_fields_are_named(tmp_path):
    path = tmp_path / "p.toml"
    path.write_text('name = "X"\nmin_salary = ""\n', encoding="utf-8")
    with pytest.raises(candidate_profile.ProfileError) as err:
        candidate_profile.load_profile(str(path))
    for field in ("contact_line", "home_base", "min_salary", "candidate_profile"):
        assert field in str(err.value)


def test_invalid_toml_is_reported(tmp_path):
    path = tmp_path / "p.toml"
    path.write_text('name = "unterminated\n', encoding="utf-8")
    with pytest.raises(candidate_profile.ProfileError, match="could not be read"):
        candidate_profile.load_profile(str(path))


@pytest.mark.parametrize("name, prefix", [
    ("Jane Example", "Jane_Example"),
    ("Jane Q. Example", "Jane_Example"),
    ("Cher", "Cher"),
    ("Anne-Marie O'Neil", "Anne-Marie_ONeil"),
])
def test_default_filename_prefix(name, prefix):
    assert candidate_profile.default_filename_prefix(name) == prefix


def test_explicit_filename_prefix_is_made_safe(tmp_path, monkeypatch):
    path = tmp_path / "p.toml"
    path.write_text(open(config.PROFILE_PATH, encoding="utf-8").read() + '\nfilename_prefix = "J/Example"\n',
                    encoding="utf-8")
    monkeypatch.setattr(config, "PROFILE_PATH", str(path))
    assert utils.cv_filename_base("PM", "Acme") == "J_Example_PM_Acme"


# --- Where the profile is used ----------------------------------------------------------

def test_stress_test_prompt_gets_the_profile(fake_client):
    client = fake_client('{"overall": "PASS", "verdict": "ok", "parameters": []}')
    stress_test.run_stress_test("THE JD", client)
    prompt = client.prompts[0]
    assert "CANDIDATE PROFILE:\n- TEST PROFILE LINE: based in Testby\n\nJOB DESCRIPTION:" in prompt
    assert "within approximately 60 minutes from Testby Station?" in prompt
    assert "at or below 12,345 DKK per month (base" in prompt


def test_cover_letter_uses_profile_name_and_contact(tmp_path):
    from docx import Document
    path = str(tmp_path / "letter.docx")
    generate_cover_letter.build_cover_letter_docx("Body.", "PM", "Acme", path)
    texts = [p.text for p in Document(path).paragraphs]
    assert texts[0] == "Jane Example"
    assert texts[1] == "+45 00 00 00 00  ·  jane@example.com  ·  Copenhagen"
    assert texts[-1] == "Jane Example"


# --- Privacy guard ------------------------------------------------------------------------

def _repo_text_files():
    """Every file that is, or could be, committed (tracked + untracked, not ignored)."""
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                             cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout
        names = out.splitlines()
    except (OSError, subprocess.CalledProcessError):
        names = [os.path.relpath(os.path.join(root, f), REPO_ROOT)
                 for root, dirs, files in os.walk(REPO_ROOT)
                 if not any(part in root for part in ("node_modules", ".venv", ".git"))
                 for f in files]
    for name in names:
        path = os.path.join(REPO_ROOT, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                yield name, f.read()
        except UnicodeDecodeError:
            continue  # binary file


PHONE = re.compile(r"\+\d{2}[\s-]?(?:\d[\s-]?){8}")
EMAIL = re.compile(r"[\w.+-]+@([\w-]+\.)+[a-z]{2,}", re.IGNORECASE)
PLACEHOLDER_EMAIL_DOMAINS = ("example.com", "example.org", "anthropic.com")  # last: commit trailers


def test_no_real_phone_numbers_or_emails_in_the_repo():
    leaks = []
    for name, text in _repo_text_files():
        for m in PHONE.finditer(text):
            if set(re.sub(r"\D", "", m.group())[2:]) != {"0"}:
                leaks.append(f"{name}: phone {m.group()!r}")
        for m in EMAIL.finditer(text):
            if not m.group().lower().endswith(PLACEHOLDER_EMAIL_DOMAINS):
                leaks.append(f"{name}: email {m.group()!r}")
    assert not leaks, "Personal details belong in cv-inputs/profile.toml:\n" + "\n".join(leaks)


REAL_PROFILE = os.path.join(config.INPUTS_DIR, "profile.toml")


@pytest.mark.skipif(not os.path.exists(REAL_PROFILE), reason="no private profile on this machine")
def test_real_profile_values_never_appear_in_the_repo():
    real = candidate_profile.load_profile(REAL_PROFILE)
    # The name is deliberately public (LICENSE copyright line), so it isn't checked.
    secrets = [real["contact_line"], real["home_base"], real["min_salary"]]
    secrets += [line.strip("- ").strip() for line in real["candidate_profile"].splitlines()
                if len(line.strip()) > 30]
    leaks = [f"{name}: {secret[:40]!r}…"
             for name, text in _repo_text_files()
             for secret in secrets if secret and secret in text]
    assert not leaks, "Private profile values found in the repository:\n" + "\n".join(leaks)
