#!/bin/zsh
set -e
cd "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  if command -v python3.12 >/dev/null 2>&1; then
    transcriber_python=python3.12
  elif command -v python3.13 >/dev/null 2>&1; then
    transcriber_python=python3.13
  else
    transcriber_python=python3
  fi
  "$transcriber_python" -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
fi
.venv/bin/python run.py
