import os

# Base directory — one level above the repo
BASE_DIR = os.path.join(os.path.dirname(__file__), "..")

# Input and output folders
INPUTS_DIR = os.path.abspath(os.path.join(BASE_DIR, "cv-inputs"))
OUTPUTS_DIR = os.path.abspath(os.path.join(BASE_DIR, "cv-outputs"))

# Input files
CV_PATH = os.path.join(INPUTS_DIR, "master_cv.docx")
JD_PATH = os.path.join(INPUTS_DIR, "job_description.txt")