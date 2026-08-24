from __future__ import annotations

import math
import subprocess
from pathlib import Path

from .media import MediaError, require_ffmpeg

CHUNK_SECONDS = 600
OVERLAP_SECONDS = 3


def plan_chunks(duration: float, chunk_seconds: int = CHUNK_SECONDS, overlap_seconds: int = OVERLAP_SECONDS) -> list[dict]:
    count = max(1, math.ceil(duration / chunk_seconds))
    chunks = []
    for index in range(count):
        start = index * chunk_seconds
        end = min(duration, (index + 1) * chunk_seconds + (overlap_seconds if index < count - 1 else 0))
        chunks.append({
            "chunk_id": index + 1,
            "start": float(start),
            "end": float(end),
            "status": "waiting",
            "output": f"chunk_{index + 1:04d}.json",
            "file": f"chunk_{index + 1:04d}.wav",
            "error": None,
        })
    return chunks


def create_chunk(audio: Path, output: Path, start: float, end: float) -> None:
    require_ffmpeg()
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.3f}", "-i", str(audio), "-t", f"{end - start:.3f}",
        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(output),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        output.unlink(missing_ok=True)
        raise MediaError(f"Could not create chunk: {exc.stderr.strip()}") from exc
