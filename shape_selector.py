import json
import os
import random

from config import OUTPUTS_DIR
from utils import (
    CV_TAILOR_DIR,
    SENIORITY_TIERS,
    PROBLEM_SPECIFICITY,
    DEFAULT_SENIORITY,
    DEFAULT_PROBLEM_SPECIFICITY,
    DEFAULT_AGENCY_POSTED,
)

SHAPES_DIR = os.path.join(CV_TAILOR_DIR, "cover_letter_shapes")
WEIGHTS_PATH = os.path.join(CV_TAILOR_DIR, "cover_letter_weights.txt")

# Remembers the last shape used so the same one isn't picked twice in a row.
# Lives next to the outputs (outside the repo), never committed.
STATE_PATH = os.path.join(OUTPUTS_DIR, ".cover_letter_state.json")


def list_shapes():
    """Return the names of all available cover letter shapes, i.e. every
    .txt file in the cover_letter_shapes folder (without the extension)."""
    if not os.path.isdir(SHAPES_DIR):
        return []
    return sorted(
        os.path.splitext(f)[0]
        for f in os.listdir(SHAPES_DIR)
        if f.endswith(".txt")
    )


def load_weight_rows(path=WEIGHTS_PATH, available=None):
    """Parse cover_letter_weights.txt into a list of rows, in file order.
    Raises ValueError with the line number if anything is malformed, so a typo
    in the file is caught straight away rather than silently ignored."""
    if available is None:
        available = list_shapes()

    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f, start=1):
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue

            def fail(message):
                raise ValueError(f"{os.path.basename(path)} line {line_no}: {message}")

            parts = [p.strip().lower() for p in line.split("|")]
            if len(parts) != 4:
                fail("expected 4 fields separated by '|' (seniority | problem | agency | weights)")
            seniority, problem, agency, weights_text = parts

            if seniority != "*" and seniority not in SENIORITY_TIERS:
                fail(f"seniority must be one of {', '.join(SENIORITY_TIERS)} or *, got '{seniority}'")
            if problem != "*" and problem not in PROBLEM_SPECIFICITY:
                fail(f"problem must be one of {', '.join(PROBLEM_SPECIFICITY)} or *, got '{problem}'")
            if agency not in ("yes", "no", "*"):
                fail(f"agency must be yes, no or *, got '{agency}'")

            weights = {}
            for item in weights_text.split(","):
                item = item.strip()
                if not item:
                    continue
                name, sep, weight_text = item.partition(":")
                name, weight_text = name.strip(), weight_text.strip()
                if not sep or not weight_text:
                    fail(f"'{item}' should look like shape_name:weight")
                if name not in available:
                    fail(f"unknown shape '{name}'. Available shapes: {', '.join(available)}")
                try:
                    weight = float(weight_text)
                except ValueError:
                    fail(f"weight for '{name}' must be a number, got '{weight_text}'")
                if weight < 0:
                    fail(f"weight for '{name}' cannot be negative")
                if weight > 0:
                    weights[name] = weight

            if not weights:
                fail("row has no shape with a weight above zero")

            rows.append({
                "seniority": seniority,
                "problem": problem,
                "agency": agency,
                "weights": weights,
            })
    return rows


def _row_matches(row, seniority, problem, agency_posted):
    agency_value = "yes" if agency_posted else "no"
    return (
        row["seniority"] in ("*", seniority)
        and row["problem"] in ("*", problem)
        and row["agency"] in ("*", agency_value)
    )


def read_last_shape():
    """The shape used for the previous letter, or None if unknown."""
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("last_shape")
    except (OSError, ValueError, AttributeError):
        return None


def record_shape_used(shape):
    """Remember which shape was just used. Best effort only: a locked or
    unwritable file (e.g. a OneDrive sync lock) must never stop a letter
    from being generated."""
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump({"last_shape": shape}, f)
    except (OSError, ValueError):
        pass


def select_shape(job_details=None, avoid_last=True, rng=None):
    """Pick a cover letter shape for this role by weighted random choice.

    job_details is the dict returned by utils.extract_job_details(). If it is
    None, or lacks the classification fields, neutral defaults are used.

    Returns (shape_name, reason) where reason is a short human-readable
    description of how the choice was made."""
    rng = rng or random
    details = job_details or {}

    seniority = details.get("seniority_tier", DEFAULT_SENIORITY)
    problem = details.get("problem_specificity", DEFAULT_PROBLEM_SPECIFICITY)
    agency_posted = details.get("agency_posted", DEFAULT_AGENCY_POSTED)

    available = list_shapes()
    if not available:
        raise ValueError(f"No cover letter shapes found in {SHAPES_DIR}")

    rows = load_weight_rows(available=available)
    row = next((r for r in rows if _row_matches(r, seniority, problem, agency_posted)), None)
    weights = dict(row["weights"]) if row else {name: 1.0 for name in available}

    last = read_last_shape() if avoid_last else None
    candidates = {name: w for name, w in weights.items() if name != last}
    if not candidates:  # a single-shape row: allow the repeat
        candidates = weights

    shape = rng.choices(list(candidates), weights=list(candidates.values()), k=1)[0]

    role_description = (
        f"{seniority} role, {problem} JD, "
        f"{'agency-posted' if agency_posted else 'direct posting'}"
    )
    return shape, role_description