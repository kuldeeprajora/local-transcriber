#!/bin/zsh

cd "${0:A:h}"
setup_log="$PWD/setup-mac.log"
venv_python="$PWD/.venv/bin/python"
print "Local Transcriber Mac setup started $(date)" > "$setup_log"

pause_and_exit() {
  local exit_code="$1"
  echo
  read "?Press Enter to close..."
  exit "$exit_code"
}

detect_python() {
  local candidate
  for candidate in python3.12 python3.13 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 9))' >/dev/null 2>&1; then
      transcriber_python="$candidate"
      return 0
    fi
  done
  return 1
}

verify_packages() {
  "$venv_python" -c 'import fastapi, importlib.util, multipart, platform, psutil, uvicorn; required = "mlx_whisper" if platform.system() == "Darwin" and platform.machine().lower() in {"arm64", "aarch64"} else "faster_whisper"; assert importlib.util.find_spec(required); print(f"Python transcription packages: READY ({required})")'
}

echo "============================================================"
echo "          LOCAL TRANSCRIBER - SAFE MAC SETUP"
echo "============================================================"
echo "This installer tries automatic recovery before it stops."
echo "Diagnostic log: $setup_log"
echo

echo "[1/5] Finding a compatible Python..."
if ! detect_python; then
  if command -v brew >/dev/null 2>&1; then
    echo "Python was not found. Trying: brew install python@3.12"
    brew install python@3.12
    print "Homebrew Python install exit code: $?" >> "$setup_log"
    hash -r
    detect_python || true
  fi
fi

if [[ -z "${transcriber_python:-}" ]]; then
  echo "Python automatic installation was unavailable or unsuccessful." >> "$setup_log"
  echo
  echo "SETUP NEEDS ONE MANUAL STEP: PYTHON"
  echo "Install Python 3.12 from https://python.org/downloads/macos/"
  echo "Then run this installer again; it will continue automatically."
  command -v open >/dev/null 2>&1 && open "https://www.python.org/downloads/macos/"
  pause_and_exit 1
fi
echo "Using: $($transcriber_python --version)"

echo
echo "[2/5] Checking the private Python environment..."
if [[ -e .venv && ! -x "$venv_python" ]] || { [[ -x "$venv_python" ]] && ! "$venv_python" -c 'import sys' >/dev/null 2>&1; }; then
  venv_backup=".venv-broken-$(date +%Y%m%d-%H%M%S)"
  echo "Existing .venv is invalid. Preserving it as $venv_backup..."
  mv .venv "$venv_backup" || {
    echo "Could not preserve the broken .venv." >> "$setup_log"
    echo "Close programs using this folder and check file permissions."
    pause_and_exit 1
  }
fi

if [[ ! -x "$venv_python" ]]; then
  echo "Creating .venv..."
  "$transcriber_python" -m venv .venv || {
    echo "First environment command failed. Trying ensurepip and venv again..."
    "$transcriber_python" -m ensurepip --upgrade >/dev/null 2>&1 || true
    "$transcriber_python" -m venv --clear .venv
  }
fi
if [[ ! -x "$venv_python" ]]; then
  echo "Could not create .venv." >> "$setup_log"
  echo "SETUP FAILED: check disk space and folder permissions."
  pause_and_exit 1
fi

echo
echo "[3/5] Installing Python dependencies..."
"$venv_python" -m ensurepip --upgrade >/dev/null 2>&1 || true
"$venv_python" -m pip install --upgrade pip setuptools wheel || echo "WARNING: pip upgrade failed; continuing with the existing pip."

if ! "$venv_python" -m pip install --retries 4 --timeout 60 -r requirements.txt; then
  echo "First dependency installation failed."
  echo "Retrying without the pip download cache..."
  "$venv_python" -m pip cache purge >/dev/null 2>&1 || true
  "$venv_python" -m pip install --no-cache-dir --retries 6 --timeout 90 -r requirements.txt || {
    echo "Dependency installation failed after both attempts." >> "$setup_log"
    echo "SETUP FAILED: check internet, VPN, proxy, security software, and disk space."
    pause_and_exit 1
  }
fi

echo
echo "[4/5] Verifying the transcription backend..."
if ! verify_packages; then
  echo "Verification failed. Reinstalling the selected backend..."
  if [[ "$(uname -m)" == "arm64" ]]; then
    backend_package="mlx-whisper"
  else
    backend_package="faster-whisper"
  fi
  "$venv_python" -m pip install --no-cache-dir --force-reinstall "$backend_package" fastapi "uvicorn[standard]" python-multipart psutil || {
    echo "Backend forced reinstall failed." >> "$setup_log"
    echo "SETUP FAILED: send setup-mac.log and the error above to the administrator."
    pause_and_exit 1
  }
  verify_packages || {
    echo "Backend verification failed after repair." >> "$setup_log"
    echo "SETUP FAILED: send setup-mac.log and the error above to the administrator."
    pause_and_exit 1
  }
fi

echo
echo "[5/5] Checking FFmpeg and FFprobe..."
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "FFmpeg is missing. Trying: brew install ffmpeg"
    brew install ffmpeg
    print "Homebrew FFmpeg install exit code: $?" >> "$setup_log"
    hash -r
  else
    echo "FFmpeg is missing and Homebrew is unavailable." >> "$setup_log"
    echo
    echo "PYTHON IS READY - FFMPEG NEEDS ONE MANUAL STEP"
    echo "Install Homebrew from https://brew.sh/ and run: brew install ffmpeg"
    command -v open >/dev/null 2>&1 && open "https://brew.sh/"
    pause_and_exit 2
  fi
fi

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "FFmpeg remained unavailable after Homebrew installation." >> "$setup_log"
  echo "PYTHON IS READY, but FFmpeg still needs attention."
  echo "Run: brew install ffmpeg"
  pause_and_exit 2
fi

echo "FFmpeg and FFprobe: READY"
print "Setup completed successfully." >> "$setup_log"
echo
echo "============================================================"
echo "SETUP COMPLETE"
echo "Now double-click start-macos.command"
echo "============================================================"
pause_and_exit 0
