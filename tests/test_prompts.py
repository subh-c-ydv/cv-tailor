"""Guards for the editable prompt files. A stray { or } added while editing a
prompt breaks str.format() at run time, mid-pipeline; these tests catch it
as soon as the file is saved."""
import string

import pytest

import utils

EXPECTED_PLACEHOLDERS = {
    "prompt_config.txt": {"jd_text", "tagline_text", "core_competencies_text", "summary_text",
                          "experience_text", "missing_keywords", "gaps"},
    "cover_letter_prompt.txt": {"jd_text", "cv_text", "job_title", "company_name",
                                "missing_keywords", "gaps", "shape_instructions"},
    "stress_test_prompt.txt": {"jd_text"},
    "keyword_match_prompt.txt": {"jd_text", "cv_text"},
}


def _placeholders(template):
    return {field for _, field, _, _ in string.Formatter().parse(template) if field is not None}


@pytest.mark.parametrize("name", sorted(EXPECTED_PLACEHOLDERS))
def test_prompt_placeholders(name):
    template = utils.load_prompt(name)
    try:
        found = _placeholders(template)
    except ValueError as e:
        pytest.fail(f"{name} has an unbalanced brace ({e}). Literal braces must be doubled: {{{{ }}}}")
    assert found == EXPECTED_PLACEHOLDERS[name], (
        f"{name}: unexpected {sorted(found - EXPECTED_PLACEHOLDERS[name])}, "
        f"missing {sorted(EXPECTED_PLACEHOLDERS[name] - found)}"
    )


@pytest.mark.parametrize("name", sorted(EXPECTED_PLACEHOLDERS))
def test_prompt_formats_with_braces_in_inputs(name):
    """JDs can contain braces; values are inserted literally and must not break formatting."""
    values = {key: "{weird} JD text }{" for key in EXPECTED_PLACEHOLDERS[name]}
    rendered = utils.load_prompt(name).format(**values)
    assert "{weird} JD text }{" in rendered


@pytest.mark.parametrize("name", sorted(EXPECTED_PLACEHOLDERS) + ["cv_structure.txt", "cover_letter_weights.txt"])
def test_prompt_files_are_valid_utf8(name):
    with open(utils.app_file(name), "rb") as f:
        f.read().decode("utf-8")


@pytest.mark.parametrize("rule", [
    '"CIO-1 level"',
    "Digital Products Portfolio (DPP)",
    "below 14 days",
    "Infosys",
    "P&L",
    "CSM",
])
def test_fixed_factual_rules_are_still_in_the_cv_prompt(rule):
    """The fact checker enforces these rules; the prompt must keep asking for them."""
    assert rule in utils.load_prompt("prompt_config.txt")
