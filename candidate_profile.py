"""The candidate's personal details, kept out of the repository.

They live in cv-inputs/profile.toml, next to the master CV (outside the repo,
never committed). profile.example.toml in the repo shows the format.

Used for:
  - the cover letter header and sign-off (name, contact line)
  - output file names (filename_prefix)
  - the stress test (candidate_profile, home_base, min_salary)
"""
import os
import re
import tomllib

import config

REQUIRED_FIELDS = ("name", "contact_line", "home_base", "min_salary", "candidate_profile")


class ProfileError(RuntimeError):
    pass


def default_filename_prefix(name):
    """'Jane Q. Example' -> 'Jane_Example' (first and last name)."""
    words = [re.sub(r"[^\w-]", "", w) for w in str(name).split()]
    words = [w for w in words if w]
    if not words:
        return "CV"
    return "_".join([words[0], words[-1]] if len(words) > 1 else words)


def load_profile(path=None):
    """Read and validate profile.toml. Read fresh on every call, so edits to
    the file take effect on the next run without restarting the app."""
    path = path or config.PROFILE_PATH
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        raise ProfileError(
            f"Your profile file was not found at {path}. Copy profile.example.toml from the "
            "CV Tailor folder to that location and fill in your details."
        )
    except tomllib.TOMLDecodeError as e:
        raise ProfileError(f"{os.path.basename(path)} could not be read: {e}")

    missing = [k for k in REQUIRED_FIELDS if not str(data.get(k, "")).strip()]
    if missing:
        raise ProfileError(f"{os.path.basename(path)} is missing: {', '.join(missing)}")

    profile = {k: str(data[k]).strip() for k in REQUIRED_FIELDS}
    prefix = str(data.get("filename_prefix", "")).strip()
    profile["filename_prefix"] = re.sub(r"[^\w-]", "_", prefix) if prefix else default_filename_prefix(profile["name"])
    return profile
