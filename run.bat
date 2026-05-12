@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM run.bat  —  One-shot launcher for Squad Flow Metrics (Windows)
REM
REM Usage:  double-click run.bat  OR  run it from a command prompt
REM
REM Requires Python 3.11+ to be on the PATH (python.org installer recommended).
REM ─────────────────────────────────────────────────────────────────────────────

cd /d "%~dp0"

SET VENV_DIR=.venv
SET PYTHON=%VENV_DIR%\Scripts\python.exe
SET PIP=%VENV_DIR%\Scripts\pip.exe
SET STREAMLIT=%VENV_DIR%\Scripts\streamlit.exe

REM ── 1. Create venv if missing ─────────────────────────────────────────────
IF NOT EXIST "%PYTHON%" (
    echo Creating virtual environment in %VENV_DIR%\ ...
    python -m venv %VENV_DIR%
)

REM ── 2. Install / upgrade dependencies ────────────────────────────────────
echo Installing dependencies ...
"%PIP%" install --quiet --upgrade pip
"%PIP%" install --quiet -r requirements.txt

REM ── 3. Launch ─────────────────────────────────────────────────────────────
echo.
echo Starting Squad Flow Metrics at http://localhost:8501
echo Press Ctrl+C to stop.
echo.
"%STREAMLIT%" run app.py

pause
