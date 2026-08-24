#!/bin/zsh

cd "${0:A:h}"

echo "============================================================"
echo "                LOCAL TRANSCRIBER - MAC SETUP"
echo "============================================================"
echo
echo "This will create a private Python environment and install all"
echo "dependencies required by Local Transcriber."
echo

if command -v python3.12 >/dev/null 2>&1; then
  transcriber_python=python3.12
elif command -v python3.13 >/dev/null 2>&1; then
  transcriber_python=python3.13
elif command -v python3 >/dev/null 2>&1; then
  transcriber_python=python3
else
  echo "SETUP FAILED: Python was not found."
  echo "Install Python 3.12 from https://python.org/downloads/macos/"
  echo
  read "?Press Enter to close..."
  exit 1
fi

echo "Using: $($transcriber_python --version)"

if [[ ! -x .venv/bin/python ]]; then
  echo "[1/4] Creating the Python environment..."
  "$transcriber_python" -m venv .venv || {
    echo "SETUP FAILED while creating .venv"
    read "?Press Enter to close..."
    exit 1
  }
else
  echo "[1/4] Existing Python environment found."
fi

echo "[2/4] Updating the package installer..."
.venv/bin/python -m pip install --upgrade pip || {
  echo "SETUP FAILED while updating pip."
  read "?Press Enter to close..."
  exit 1
}

echo "[3/4] Installing Local Transcriber dependencies..."
.venv/bin/python -m pip install -r requirements.txt || {
  echo "SETUP FAILED while installing dependencies."
  echo "Check the internet connection and the error shown above."
  read "?Press Enter to close..."
  exit 1
}

echo "[4/4] Checking the installation..."
.venv/bin/python -c 'import fastapi, importlib.util, platform, uvicorn; required = "mlx_whisper" if platform.system() == "Darwin" and platform.machine().lower() in {"arm64", "aarch64"} else "faster_whisper"; assert importlib.util.find_spec(required); print(f"Python transcription packages: READY ({required})")' || {
  echo "SETUP FAILED: the transcription backend could not be imported."
  read "?Press Enter to close..."
  exit 1
}

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo
  echo "============================================================"
  echo "PYTHON SETUP COMPLETE - FFMPEG STILL NEEDED"
  echo "Install Homebrew from https://brew.sh/ and run: brew install ffmpeg"
  echo "Then close this window and run this installer again."
  echo "============================================================"
  echo
  read "?Press Enter to close..."
  exit 2
fi

echo "FFmpeg and FFprobe: READY"
echo
echo "============================================================"
echo "SETUP COMPLETE"
echo "You can now double-click start-macos.command"
echo "============================================================"
echo
read "?Press Enter to close..."
