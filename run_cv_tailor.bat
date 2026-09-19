@echo off
REM Portable launcher for Windows (double-clickable)
cd /d "%~dp0"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
streamlit run app.py --server.port 8501
