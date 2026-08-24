# Local Transcriber

A private, resumable transcription tool for macOS and Windows (Linux is also supported). It detects the available Apple, NVIDIA, or CPU hardware at launch, selects an appropriate Whisper model and compute precision, and keeps media, chunks, transcripts, and exports on the computer.

For a non-technical handoff with separate Mac and Windows instructions, see [`COLLEAGUE_SETUP_GUIDE.md`](COLLEAGUE_SETUP_GUIDE.md).

## Automatic runtime selection

| Hardware | Backend | Auto mode |
|---|---|---|
| Apple Silicon | MLX Whisper | Large-v3 Turbo below 24 GB; Large-v3 at 24 GB or more |
| NVIDIA GPU with working CUDA | Faster Whisper / CTranslate2 | Turbo or Small based on VRAM, using FP16 or INT8-FP16 |
| Windows/macOS/Linux CPU | Faster Whisper / CTranslate2 | Medium on capable 16 GB / 8-thread systems; Small otherwise, using INT8 |

If an NVIDIA GPU is present but the CUDA runtime is unavailable, the app safely falls back to CPU. Restarting after CUDA is configured enables the GPU automatically.

## Requirements

- Python 3.11–3.13 (3.12 recommended)
- FFmpeg, including `ffprobe`
- Enough free disk space for a 16 kHz mono WAV, chunks, and the selected model
- For NVIDIA acceleration: CUDA 12 and cuDNN 9

Install FFmpeg on macOS with `brew install ffmpeg`. On Windows, install a current FFmpeg build and make sure both `ffmpeg.exe` and `ffprobe.exe` are on `PATH`.

## Install and run

### macOS

For the first setup, double-click `INSTALL-MAC.command`. After it reports success, use `start-macos.command` for normal launches. Or run the commands manually:

```bash
cd /path/to/transcriber
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python run.py
```

### Windows

For the first setup, double-click `INSTALL-WINDOWS.bat`. After it reports success, use `start-windows.bat` for normal launches. Or run the equivalent commands manually in PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run.py
```

Open [http://localhost:8000](http://localhost:8000). The first transcription downloads the selected model; later runs use the local model cache and can work offline.

## Job storage and recovery

Each job is isolated under `data/jobs/<job-id>/`:

```text
job.json          atomic state updated after every chunk
source/           original imported media
audio/            extracted 16 kHz mono WAV
chunks/           overlapping 10-minute WAV chunks
results/          per-chunk JSON and merged transcript
exports/          TXT, SRT and full JSON
```

Interrupted active jobs resume at launch. Completed chunks are skipped. Memory pressure triggers one retry after cache cleanup and then a model fallback, which is recorded in the job and shown in the UI.

## Quality modes

- **Auto:** balances accuracy and speed for the detected RAM, VRAM, and CPU threads.
- **Accurate:** selects Large-v3 where practical, or a memory-appropriate accurate model.
- **Fast:** selects a lighter model for turnaround speed.
- **Hindi + English:** uses a Hindi/English domain prompt and always transcribes rather than translates.

Completed transcripts receive a deterministic quality report. Repetition loops and invalid text are flagged for review rather than silently rewritten.

## Tests

The core tests do not download a model:

```bash
pytest -q
```

The server binds only to `127.0.0.1`. There is no telemetry or paid transcription API; network access is needed only for the initial model download.
