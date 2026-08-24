from __future__ import annotations

import json
from pathlib import Path


def _srt_time(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_exports(job: dict, transcript: dict, directory: Path) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    txt_path = directory / "transcript.txt"
    srt_path = directory / "transcript.srt"
    json_path = directory / "transcript.json"

    txt_path.write_text("\n\n".join(s["text"] for s in transcript["segments"]) + "\n", encoding="utf-8")
    blocks = []
    for index, segment in enumerate(transcript["segments"], 1):
        blocks.append(
            f"{index}\n{_srt_time(segment['start'])} --> {_srt_time(segment['end'])}\n{segment['text']}"
        )
    srt_path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    master = {
        "job_id": job["id"],
        "source": job["filename"],
        "duration": job.get("media", {}).get("duration"),
        "model": job.get("model"),
        "language_mode": job.get("language"),
        **transcript,
    }
    json_path.write_text(json.dumps(master, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"txt": txt_path.name, "srt": srt_path.name, "json": json_path.name}
