import os
from dotenv import load_dotenv

# Folder containing this code. Every bundled file (prompts, cover letter
# shapes, Node.js build scripts) is resolved relative to it, so the app works
# no matter which directory it is started from.
APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Load ANTHROPIC_API_KEY (and any other secrets) from the .env file next to
# this code. Keeps secrets out of git and out of OS-specific keychains, so this
# works the same way on macOS, the Mac mini, and Windows.
load_dotenv(os.path.join(APP_DIR, ".env"))

# Base directory — one level above the repo
BASE_DIR = os.path.dirname(APP_DIR)

# Input and output folders
INPUTS_DIR = os.path.join(BASE_DIR, "cv-inputs")
OUTPUTS_DIR = os.path.join(BASE_DIR, "cv-outputs")
JDS_DIR = os.path.join(INPUTS_DIR, "jds")

# Input files
CV_PATH = os.path.join(INPUTS_DIR, "master_cv.docx")
JD_PATH = os.path.join(INPUTS_DIR, "job_description.txt")

# Scratch file handed from Python to the Node.js document builders, which
# read it from their working directory (APP_DIR).
CV_DATA_PATH = os.path.join(APP_DIR, "cv_data.json")

# Claude model used for every step of the pipeline.
CLAUDE_MODEL = "claude-sonnet-4-6"
