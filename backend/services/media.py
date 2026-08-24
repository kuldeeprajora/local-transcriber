from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".mp3", ".wav", ".m4a"}


class MediaError(RuntimeError):
    pass


def require_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise MediaError("FFmpeg and ffprobe are required. Install them with: brew install ffmpeg")


def probe_media(path: Path) -> dict:
    require_ffmpeg()
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise MediaError(f"Unsupported file type: {path.suffix or 'unknown'}")
    command = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,size,format_name:stream=codec_type,codec_name,sample_rate,channels,width,height",
        "-of", "json", str(path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        data = json.loads(result.stdout)
        duration = float(data.get("format", {}).get("duration", 0))
    except (subprocess.CalledProcessError, ValueError, json.JSONDecodeError) as exc:
        detail = getattr(exc, "stderr", "") or "FFmpeg could not read this file."
        raise MediaError(f"Unsupported or corrupt media: {detail.strip()}") from exc
    if duration <= 0 or not any(s.get("codec_type") == "audio" for s in data.get("streams", [])):
        raise MediaError("The selected file has no readable audio track.")
    return {
        "duration": duration,
        "size": int(data.get("format", {}).get("size", path.stat().st_size)),
        "format": data.get("format", {}).get("format_name", "unknown"),
        "streams": data.get("streams", []),
    }


def extract_audio(source: Path, output: Path) -> None:
    require_ffmpeg()
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(source), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(output),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        output.unlink(missing_ok=True)
        if shutil.disk_usage(output.parent).free < 512 * 1024**2:
            raise MediaError("Audio extraction stopped because disk space is critically low.") from exc
        raise MediaError(f"Audio extraction failed: {exc.stderr.strip()}") from exc
