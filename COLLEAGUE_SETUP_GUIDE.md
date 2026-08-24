# Local Transcriber — Mac and Windows Setup Guide

This guide is written for someone receiving a copy of the Local Transcriber folder for the first time. The tool runs locally: recordings and transcripts are not sent to a paid transcription API.

## What should be included in the shared folder

Send the project files, including:

- `backend/`
- `frontend/`
- `config/`
- `requirements.txt`
- `run.py`
- `INSTALL-MAC.command`
- `INSTALL-WINDOWS.bat`
- `start-macos.command`
- `start-windows.bat`

Do **not** send these folders from another computer:

- `.venv/` — it contains machine- and operating-system-specific packages
- `data/jobs/` — it may contain private recordings and transcripts
- `__pycache__/` and `.pytest_cache/` — temporary files

Compress the cleaned project folder as a ZIP. The recipient should extract the ZIP before running it; do not run the tool from inside the ZIP preview.

## Before starting

The computer needs:

1. Python 3.12, 64-bit
2. FFmpeg and FFprobe
3. An internet connection for the first setup and first model download
4. Several gigabytes of free space for models, extracted audio, and transcripts

The app detects the hardware automatically:

- Apple Silicon uses the Apple MLX backend.
- A supported NVIDIA GPU with CUDA uses GPU acceleration.
- Other Windows and Mac computers use the CPU backend.
- If NVIDIA CUDA is incomplete, the tool falls back to CPU instead of refusing to run.

---

# Windows setup

## 1. Extract the project

Extract the ZIP to a short, normal folder path, for example:

```text
C:\LocalTranscriber
```

Avoid OneDrive-synced folders for the first setup if possible.

## 2. Install Python 3.12

Download a 64-bit Python 3.12 installer from the official Python Windows downloads page:

https://www.python.org/downloads/windows/

During installation, enable the option that adds Python to `PATH` or installs the Python launcher. Restart Command Prompt after installation.

Verify it by opening **Command Prompt** and running:

```bat
py -3.12 --version
```

It should print `Python 3.12.x`.

## 3. Install FFmpeg

Open **PowerShell** or **Command Prompt** and run:

```bat
winget install -e --id Gyan.FFmpeg
```

Close and reopen the terminal, then verify both programs:

```bat
ffmpeg -version
ffprobe -version
```

If `winget` is unavailable, use one of the Windows builds linked by the official FFmpeg download page and add its `bin` directory to the Windows `PATH`:

https://ffmpeg.org/download.html

## 4. Start Local Transcriber

Open the extracted `LocalTranscriber` folder. For the first setup, double-click:

```text
INSTALL-WINDOWS.bat
```

Wait until it reports **SETUP COMPLETE**. It verifies Python packages, FFmpeg, and FFprobe and keeps the window open if anything needs attention.

After setup, double-click:

```text
start-windows.bat
```

On the first run, the script creates a private Python environment and installs the Windows transcription backend. This can take several minutes. Keep the black Command Prompt window open.

When the server says it is running, open:

http://localhost:8000/

If the batch window closes immediately, open Command Prompt, change to the project folder, and run it there so the error remains visible:

```bat
cd C:\LocalTranscriber
start-windows.bat
```

## Optional: NVIDIA GPU acceleration

GPU acceleration is optional. The CPU mode works without CUDA.

For GPU mode, the computer needs a compatible NVIDIA driver plus the CUDA 12 cuBLAS libraries and cuDNN 9. After installing them, restart Windows and launch the tool again. The System card should show **NVIDIA CUDA**. If it shows **Faster Whisper CPU**, the app is still functional but the CUDA runtime was not detected.

Do not install CUDA merely to make the app work. Set it up only when faster NVIDIA processing is worth the additional configuration.

---

# macOS setup

Apple Silicon Macs provide the best Mac performance. Intel Macs are supported through CPU processing.

## 1. Extract the project

Double-click the ZIP and move the extracted folder somewhere permanent, for example:

```text
Documents/LocalTranscriber
```

Do not run it directly from Downloads if macOS or company security software frequently cleans that folder.

## 2. Install Python 3.12

Either download the signed Python 3.12 macOS installer from:

https://www.python.org/downloads/macos/

Or, if Homebrew is already installed, open Terminal and run:

```bash
brew install python@3.12
```

Verify the installation:

```bash
python3.12 --version
```

It should print `Python 3.12.x`.

## 3. Install FFmpeg

With Homebrew installed, run:

```bash
brew install ffmpeg
```

Verify both programs:

```bash
ffmpeg -version
ffprobe -version
```

If the `brew` command is missing, install Homebrew by following its official instructions:

https://brew.sh/

## 4. Start Local Transcriber

In Finder, first double-click:

```text
INSTALL-MAC.command
```

Wait until it reports **SETUP COMPLETE**. It verifies Python packages, FFmpeg, and FFprobe and keeps the window open if anything needs attention.

After setup, double-click:

```text
start-macos.command
```

The first launch creates a private Python environment and installs the correct transcription backend. Keep the Terminal window open.

If macOS does not allow the first double-click, right-click the `.command` file, choose **Open**, and confirm that you want to open this local script. If the file is not executable, run this once in Terminal, replacing the path with the actual project location:

```bash
chmod +x "/path/to/LocalTranscriber/start-macos.command"
chmod +x "/path/to/LocalTranscriber/INSTALL-MAC.command"
```

Then launch it again and open:

http://localhost:8000/

### Reliable manual start

If the double-click launcher reports a Python error, use Terminal:

```bash
cd "/path/to/LocalTranscriber"
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
```

---

# Everyday use after setup

1. Double-click the launcher for the operating system.
2. Keep its Command Prompt or Terminal window open.
3. Open http://localhost:8000/ in a browser.
4. Confirm that the System card says **Ready**.
5. Drop in an MP4, MOV, MKV, MP3, WAV, or M4A file.
6. Choose the language and quality mode.
7. Select **Transcribe locally**.
8. When complete, review the transcript and export TXT, SRT, or JSON.

To stop the tool, return to its terminal window and press `Ctrl+C`. Closing the terminal also stops the local server.

## Quality-mode advice

- **Auto:** recommended for most work; adapts to the computer.
- **Accurate:** use for difficult audio, Hindi-English code-switching, names, or numbers. It is slower.
- **Fast:** use for quick drafts where some recognition errors are acceptable.
- **Hindi + English:** use when speakers naturally switch between both languages.

For best accuracy, start with a clean recording, avoid very low speaker volume, and remove long music-only introductions when practical. Songs, chants, and overlapping speech are harder for speech transcription models than normal spoken dialogue.

## First transcription

The first transcription downloads the selected Whisper model. It can appear slow and requires internet access. Later runs reuse the local model cache and can work offline.

Do not close the terminal during a transcription. If the computer or app stops unexpectedly, launch it again; completed chunks are preserved and an interrupted job can resume.

## Where files are stored

Jobs are stored inside:

```text
LocalTranscriber/data/jobs/
```

That directory can contain the original recording, extracted audio, transcripts, and exports. Treat it as private data. Deleting a job folder permanently removes that job's local working files.

## Common problems

### System card says “FFmpeg missing”

Run both `ffmpeg -version` and `ffprobe -version` in a new terminal. If either command is not found, reinstall FFmpeg or correct the system `PATH`, then restart the app.

### Python is not found

Install 64-bit Python 3.12, close all terminal windows, and try again. On Windows verify `py -3.12 --version`; on Mac verify `python3.12 --version`.

### A Python package is missing

From the project folder, reinstall the requirements.

Windows:

```bat
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

macOS:

```bash
.venv/bin/python -m pip install -r requirements.txt
```

### The page does not open

Confirm that the terminal is still open and contains a line similar to:

```text
Uvicorn running on http://127.0.0.1:8000
```

Then enter `http://localhost:8000/` directly in the browser address bar. If port 8000 is already in use, close any older Local Transcriber terminal and launch it again.

### NVIDIA GPU is detected but CPU is used

The NVIDIA driver, CUDA 12 libraries, or cuDNN 9 are missing or incompatible. CPU processing remains available. If GPU processing is required, follow the current Faster Whisper GPU requirements and NVIDIA installation documentation.

### Model download fails

Check the internet connection, VPN, proxy, firewall, and available disk space. Then press Retry. Once the model has downloaded successfully, it remains cached locally.

### The transcript has poor accuracy

Try these changes in order:

1. Select the correct language mode instead of Auto detect.
2. Use **Accurate** quality.
3. Remove music-only sections and silence from the beginning.
4. Improve the source audio or use the original recording rather than a heavily compressed copy.
5. Review any quality warnings shown after completion.

## Getting help

When reporting a problem, include:

- Windows or macOS version
- CPU and GPU model
- RAM amount
- The Backend and Recommended values shown in the System card
- The complete error shown in the terminal
- Whether `python`, `ffmpeg`, and `ffprobe` verification commands worked

Do not send private recordings or the `data/jobs` folder unless sharing them has been explicitly approved.
