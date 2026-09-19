# Portable launcher for Windows (PowerShell)
# One-time setup:
#   py -m venv .venv
#   .\.venv\Scripts\Activate.ps1
#   pip install -r requirements.txt
#   Copy .env.example to .env and add your ANTHROPIC_API_KEY
#   Install Node.js (needed for the .docx export step) and make sure `node` is on PATH
#
# Then, each time:
#   .\run_cv_tailor.ps1
Set-Location -Path $PSScriptRoot
if (Test-Path ".venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
}
streamlit run app.py --server.port 8501
