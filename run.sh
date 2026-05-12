#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# run.sh  —  One-shot launcher for Squad Flow Metrics (macOS / Linux)
#
# Usage:
#   chmod +x run.sh
#   ./run.sh
#
# What it does:
#   1. Creates a .venv if one doesn't exist.
#   2. Installs / upgrades dependencies from requirements.txt.
#   3. Launches the Streamlit app.
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"
PYTHON="${VENV_DIR}/bin/python"
PIP="${VENV_DIR}/bin/pip"
STREAMLIT="${VENV_DIR}/bin/streamlit"

# ── 1. Create venv if missing ─────────────────────────────────────────────────
if [ ! -f "$PYTHON" ]; then
  echo "Creating virtual environment in ${VENV_DIR}/ ..."
  python3 -m venv "$VENV_DIR"
fi

# ── 2. Install / upgrade dependencies ────────────────────────────────────────
echo "Installing dependencies ..."
"$PIP" install --quiet --upgrade pip
"$PIP" install --quiet -r requirements.txt

# ── 3. Launch ─────────────────────────────────────────────────────────────────
echo ""
echo "Starting Squad Flow Metrics at http://localhost:8501"
echo "Press Ctrl+C to stop."
echo ""
"$STREAMLIT" run app.py
