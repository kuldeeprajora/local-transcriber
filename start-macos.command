#!/bin/zsh

cd "${0:A:h}"
venv_python="$PWD/.venv/bin/python"

ready=true
[[ -x "$venv_python" ]] || ready=false
if [[ "$ready" == true ]]; then
  "$venv_python" -c 'import fastapi, importlib.util, multipart, platform, psutil, uvicorn; required = "mlx_whisper" if platform.machine().lower() in {"arm64", "aarch64"} else "faster_whisper"; assert importlib.util.find_spec(required)' >/dev/null 2>&1 || ready=false
fi
command -v ffmpeg >/dev/null 2>&1 || ready=false
command -v ffprobe >/dev/null 2>&1 || ready=false

if [[ "$ready" != true ]]; then
  echo "Local Transcriber needs setup or repair."
  echo "Starting the safe installer..."
  echo
  zsh "$PWD/INSTALL-MAC.command"
  if [[ $? -ne 0 ]]; then
    echo
    echo "The app was not started because setup is incomplete."
    read "?Press Enter to close..."
    exit 1
  fi
fi

echo "Starting Local Transcriber at http://localhost:8000/"
"$venv_python" run.py
if [[ $? -ne 0 ]]; then
  echo
  echo "The server stopped with an error. Run INSTALL-MAC.command to repair dependencies."
  read "?Press Enter to close..."
  exit 1
fi
