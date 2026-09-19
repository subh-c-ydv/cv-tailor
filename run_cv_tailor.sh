#!/bin/bash
# Portable launcher for macOS/Linux (Mac mini, MacBook, etc.)
# Run once per machine: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
# Then just: ./run_cv_tailor.sh
cd "$(dirname "$0")"
if [ -d ".venv" ]; then
  source .venv/bin/activate
fi
streamlit run app.py --server.port 8501
