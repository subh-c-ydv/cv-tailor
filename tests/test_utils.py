import os

import pytest

import utils


# --- File and folder names ----------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("Senior PM", "Senior PM"),
    ('PM: Data/AI? "Lead"', "PM- Data-AI- -Lead-"),
    ("a<b>c|d*e\\f", "a-b-c-d-e-f"),
    ("Lead.  ", "Lead"),
    ("  many   spaces  ", "many spaces"),
    ("", "Untitled"),
    (None, "Untitled"),
    ("CON", "_CON"),
    ("lpt1", "_lpt1"),
])
def test_safe_filename(raw, expected):
    assert utils.safe_filename(raw) == expected


def test_safe_filename_truncates():
    assert len(utils.safe_filename("x" * 500, max_length=40)) == 40


def test_normal_names_are_unchanged():
    """Existing output folders keep matching for ordinary titles."""
    assert utils.cv_filename_base("Senior PM", "Maersk") == "Jane_Example_Senior_PM_Maersk"
    assert utils.cover_letter_filename("Senior PM", "Maersk") == "Jane_Example_Cover_Letter_Senior_PM_Maersk.docx"


def test_make_output_dir_creates_safe_folder(isolate):
    path = utils.make_output_dir("Lead: Data/AI?", "Acme")
    assert os.path.isdir(path)
    assert os.path.dirname(path) == str(isolate)
    assert os.path.basename(path) == "Lead- Data-AI- @ Acme"


def test_worst_case_path_stays_under_windows_limit():
    onedrive_outputs = r"C:\Users\subha\OneDrive\Documents\cv-outputs"
    title, company = "T" * 500, "C" * 500
    folder = f"{utils.safe_filename(title, 50)} @ {utils.safe_filename(company, 30)}"
    for name in (utils.cover_letter_filename(title, company),
                 utils.cv_filename_base(title, company) + "_ATS.docx"):
        assert len(os.path.join(onedrive_outputs, folder, name)) < 260


# --- Reading text -------------------------------------------------------------

def test_prompts_are_read_as_utf8():
    assert "Møller" in utils.load_prompt("prompt_config.txt")
    assert "Hørsholm" in utils.load_prompt("stress_test_prompt.txt")


@pytest.mark.parametrize("data, expected", [
    ("Job │ ø".encode("utf-8"), "Job │ ø"),
    ("\ufeffWith BOM".encode("utf-8"), "With BOM"),
    ("Café – rôle".encode("cp1252"), "Café – rôle"),
])
def test_decode_text_bytes(data, expected):
    assert utils.decode_text_bytes(data) == expected


def test_decode_text_bytes_never_raises():
    assert isinstance(utils.decode_text_bytes(bytes([0x81, 0x8D, 0x41])), str)


# --- Claude replies -------------------------------------------------------------

def test_ask_claude_returns_text(fake_client):
    client = fake_client("  hello  ")
    assert utils.ask_claude(client, "prompt", 100, "test") == "hello"
    assert client.calls[0]["model"] == utils.CLAUDE_MODEL
    assert client.calls[0]["max_tokens"] == 100


@pytest.mark.parametrize("text, stop_reason, message", [
    ('{"partial": ', "max_tokens", "cut off"),
    ("no", "refusal", "declined"),
    ("   ", "end_turn", "empty"),
])
def test_ask_claude_rejects_unusable_replies(fake_client, text, stop_reason, message):
    with pytest.raises(RuntimeError, match=message):
        utils.ask_claude(fake_client((text, stop_reason)), "prompt", 100, "test")


@pytest.mark.parametrize("text", [
    '{"a": 1}',
    '```json\n{"a": 1}\n```',
    'Here you go:\n{"a": 1}\nHope that helps.',
])
def test_parse_json_object_tolerates_wrapping(text):
    assert utils.parse_json_object(text, "test") == {"a": 1}


@pytest.mark.parametrize("text, message", [
    ("Sorry, I can't.", "No JSON"),
    ('{"a": 1,,}', "not valid JSON"),
])
def test_parse_json_object_errors_are_clear(text, message):
    with pytest.raises(ValueError, match=message):
        utils.parse_json_object(text, "test")


def test_ask_claude_json_requires_an_object(fake_client):
    with pytest.raises(ValueError):
        utils.ask_claude_json(fake_client("[1, 2]"), "p", 100, "test")


def test_get_client_without_key_explains_setup(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(RuntimeError, match=r"\.env"):
        utils.get_client()


# --- Job details ------------------------------------------------------------------

def test_extract_job_details(fake_client):
    client = fake_client('{"job_title": "Delivery Lead", "company_name": "Acme", '
                         '"seniority_tier": "MID", "problem_specificity": "specific", "agency_posted": "yes"}')
    details = utils.extract_job_details("JD TEXT", client)
    assert details == {
        "job_title": "Delivery Lead",
        "company_name": "Acme",
        "seniority_tier": "mid",
        "problem_specificity": "specific",
        "agency_posted": True,
    }
    assert "JD TEXT" in client.prompts[0]


def test_job_details_fall_back_safely():
    details = utils._normalise_job_details({
        "job_title": None, "company_name": "null",
        "seniority_tier": "executive", "problem_specificity": 3, "agency_posted": "maybe",
    })
    assert details["job_title"] == utils.UNKNOWN_TITLE
    assert details["company_name"] == utils.UNKNOWN_COMPANY
    assert details["seniority_tier"] == utils.DEFAULT_SENIORITY
    assert details["problem_specificity"] == utils.DEFAULT_PROBLEM_SPECIFICITY
    assert details["agency_posted"] is False
