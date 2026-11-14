#!/usr/bin/env bash
# Start the local web UI. Extra arguments are passed through to webapp.py.
set -euo pipefail
cd "$(dirname "$0")/.."

python_ok() {
  local candidate="$1"
  [[ -n "$candidate" ]] || return 1
  if [[ "$candidate" == */* ]]; then
    [[ -x "$candidate" ]] || return 1
  elif ! command -v "$candidate" >/dev/null 2>&1; then
    return 1
  else
    candidate="$(command -v "$candidate")"
  fi
  "$candidate" -c "import sympy, z3" >/dev/null 2>&1
}

PY=""
if python_ok "${MATH_SOLVER_PYTHON:-}"; then
  if [[ "$MATH_SOLVER_PYTHON" == */* ]]; then
    PY="$MATH_SOLVER_PYTHON"
  else
    PY="$(command -v "$MATH_SOLVER_PYTHON")"
  fi
elif python_ok "$PWD/.venv/bin/python"; then
  PY="$PWD/.venv/bin/python"
elif python_ok python3; then
  PY="$(command -v python3)"
elif python_ok python; then
  PY="$(command -v python)"
fi

if [[ -z "$PY" ]]; then
  echo
  echo "[ERROR] No Python with sympy/z3 found."
  echo "Create one from this directory:"
  echo "  python3 -m venv .venv"
  echo "  .venv/bin/python -m pip install -r requirements.txt"
  echo "Or set MATH_SOLVER_PYTHON to that interpreter."
  echo
  exit 1
fi

echo "Starting Math Solver web UI with: $PY"
echo "Add --host 0.0.0.0 to listen on the LAN. Other arguments are passed through."
echo "Press Ctrl+C to stop the server."
echo
exec "$PY" webapp.py "$@"
