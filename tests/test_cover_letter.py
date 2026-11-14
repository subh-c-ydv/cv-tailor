import random

import pytest

import generate_cover_letter
import shape_selector


# --- Weights file -------------------------------------------------------------------

def test_real_weights_file_is_valid():
    rows = shape_selector.load_weight_rows()
    assert rows, "cover_letter_weights.txt has no rows"
    last = rows[-1]
    assert (last["seniority"], last["problem"], last["agency"]) == ("*", "*", "*"), \
        "the catch-all row should stay last"


def test_every_shape_file_has_instructions():
    shapes = shape_selector.list_shapes()
    assert len(shapes) >= 2
    for shape in shapes:
        assert generate_cover_letter.load_shape(shape).strip()


def _weights(tmp_path, body):
    path = tmp_path / "weights.txt"
    path.write_text(body, encoding="utf-8")
    return str(path)


@pytest.mark.parametrize("body, message", [
    ("senior | specific | no", "expected 4 fields"),
    ("boss | * | * | story_first:1", "seniority must be"),
    ("* | vague | * | story_first:1", "problem must be"),
    ("* | * | maybe | story_first:1", "agency must be"),
    ("* | * | * | story_first", "shape_name:weight"),
    ("* | * | * | haiku_letter:1", "unknown shape"),
    ("* | * | * | story_first:lots", "must be a number"),
    ("* | * | * | story_first:-1", "cannot be negative"),
    ("* | * | * | story_first:0", "no shape with a weight above zero"),
])
def test_weight_file_typos_are_reported_with_line_number(tmp_path, body, message):
    with pytest.raises(ValueError, match=message) as err:
        shape_selector.load_weight_rows(_weights(tmp_path, "# comment\n\n" + body))
    assert "line 3" in str(err.value)


# --- Choosing a shape ---------------------------------------------------------------

def _patch_weights(monkeypatch, tmp_path, body):
    monkeypatch.setattr(shape_selector, "WEIGHTS_PATH", _weights(tmp_path, body))


def test_first_matching_row_wins(monkeypatch, tmp_path):
    _patch_weights(monkeypatch, tmp_path,
                   "* | * | yes | direct_short:1\n"
                   "senior | * | * | story_first:1\n"
                   "* | * | * | three_strengths:1\n")
    pick = lambda details: shape_selector.select_shape(details, avoid_last=False)[0]
    assert pick({"seniority_tier": "senior", "problem_specificity": "generic", "agency_posted": True}) == "direct_short"
    assert pick({"seniority_tier": "senior", "problem_specificity": "generic", "agency_posted": False}) == "story_first"
    assert pick({"seniority_tier": "junior", "problem_specificity": "generic", "agency_posted": False}) == "three_strengths"


def test_missing_details_use_neutral_defaults():
    shape, reason = shape_selector.select_shape(None, avoid_last=False, rng=random.Random(1))
    assert shape in shape_selector.list_shapes()
    assert "senior role" in reason and "direct posting" in reason


def test_same_shape_is_not_used_twice_in_a_row(monkeypatch, tmp_path):
    _patch_weights(monkeypatch, tmp_path, "* | * | * | story_first:1, direct_short:1\n")
    shape_selector.record_shape_used("story_first")
    for seed in range(20):
        assert shape_selector.select_shape({}, rng=random.Random(seed))[0] == "direct_short"


def test_single_shape_row_may_repeat(monkeypatch, tmp_path):
    _patch_weights(monkeypatch, tmp_path, "* | * | * | story_first:1\n")
    shape_selector.record_shape_used("story_first")
    assert shape_selector.select_shape({})[0] == "story_first"


def test_shape_memory_survives_a_corrupt_state_file():
    with open(shape_selector.STATE_PATH, "w", encoding="utf-8") as f:
        f.write("{not json")
    assert shape_selector.read_last_shape() is None


# --- Generating the letter ------------------------------------------------------------

def test_generate_cover_letter_builds_prompt_and_remembers_shape(fake_client):
    client = fake_client("Dear team,\n\nParagraph.")
    text = generate_cover_letter.generate_cover_letter(
        "THE JD", "THE CV", "Delivery Lead", "Acme", client,
        missing_keywords=["SAFe"], gaps="No SAFe", shape="direct_short",
    )
    prompt = client.prompts[0]
    assert text == "Dear team,\n\nParagraph."
    for expected in ("THE JD", "THE CV", "Delivery Lead", "Acme", "SAFe", "DIRECT-AND-SHORT"):
        assert expected in prompt
    assert shape_selector.read_last_shape() == "direct_short"


def test_truncated_letter_is_not_saved_and_shape_not_recorded(fake_client):
    client = fake_client(("Dear team, I am writ", "max_tokens"))
    with pytest.raises(RuntimeError, match="cut off"):
        generate_cover_letter.generate_cover_letter("JD", "CV", "PM", "Acme", client, shape="story_first")
    assert shape_selector.read_last_shape() is None


def test_unknown_shape_is_rejected(fake_client):
    with pytest.raises(ValueError, match="Unknown cover letter shape"):
        generate_cover_letter.generate_cover_letter("JD", "CV", "PM", "Acme", fake_client("x"), shape="sonnet")


def test_build_cover_letter_docx(tmp_path):
    from docx import Document
    path = str(tmp_path / "letter.docx")
    generate_cover_letter.build_cover_letter_docx("First para.\n\nSecond para.\n\n\n", "PM", "Acme", path)
    texts = [p.text for p in Document(path).paragraphs]
    assert "Re: PM — Acme" in texts
    assert texts.index("First para.") < texts.index("Second para.") < texts.index("Kind regards,")


def test_cover_letter_renders_markdown_bold(tmp_path):
    from docx import Document
    path = str(tmp_path / "letter.docx")
    generate_cover_letter.build_cover_letter_docx("I cut cycle time to **below 14 days**. Stray ** gone.",
                                                  "PM", "Acme", path)
    para = next(p for p in Document(path).paragraphs if "cycle time" in p.text)
    assert para.text == "I cut cycle time to below 14 days. Stray  gone."
    assert [r.text for r in para.runs if r.bold] == ["below 14 days"]
