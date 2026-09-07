from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class JobManager:
    def __init__(self, jobs_root: Path):
        self.jobs_root = jobs_root
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    def paths(self, job_id: str) -> dict[str, Path]:
        root = self.jobs_root / job_id
        return {
            "root": root,
            "state": root / "job.json",
            "source": root / "source",
            "audio": root / "audio",
            "chunks": root / "chunks",
            "results": root / "results",
            "exports": root / "exports",
        }

    def _lock(self, job_id: str) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(job_id, threading.RLock())

    def create(self, filename: str, stored_name: str) -> dict:
        job_id = uuid.uuid4().hex
        paths = self.paths(job_id)
        for name, path in paths.items():
            if name not in {"state"}:
                path.mkdir(parents=True, exist_ok=True)
        job = {
            "id": job_id,
            "filename": filename,
            "stored_name": stored_name,
            "status": "CREATED",
            "stage_detail": "Upload saved locally",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "language": "auto",
            "quality": "auto",
            "media": None,
            "model": None,
            "chunks": [],
            "exports": {},
            "error": None,
            "model_adjustment": None,
            "quality_report": None,
            "music_segments": [],
        }
        self.save(job)
        return job

    def clone_media(self, source_job: dict) -> dict:
        """Create a new job while reusing immutable local media from an older run."""
        cloned = self.create(source_job["filename"], source_job["stored_name"])
        old_paths, new_paths = self.paths(source_job["id"]), self.paths(cloned["id"])
        for area, filename in (("source", source_job["stored_name"]), ("audio", "audio.wav")):
            old_file, new_file = old_paths[area] / filename, new_paths[area] / filename
            if not old_file.is_file():
                continue
            try:
                os.link(old_file, new_file)
            except OSError:
                shutil.copy2(old_file, new_file)
        cloned["media"] = source_job.get("media")
        cloned["stage_detail"] = "Ready to re-transcribe from saved local media"
        self.save(cloned)
        return cloned

    def load(self, job_id: str) -> dict:
        state = self.paths(job_id)["state"]
        if not state.is_file():
            raise FileNotFoundError(job_id)
        with self._lock(job_id):
            return json.loads(state.read_text(encoding="utf-8"))

    def save(self, job: dict) -> None:
        job["updated_at"] = utc_now()
        state = self.paths(job["id"])["state"]
        state.parent.mkdir(parents=True, exist_ok=True)
        temp = state.with_suffix(".tmp")
        with self._lock(job["id"]):
            temp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp, state)

    def update(self, job_id: str, **changes) -> dict:
        with self._lock(job_id):
            job = self.load(job_id)
            job.update(changes)
            self.save(job)
            return job

    def list(self) -> list[dict]:
        jobs = []
        for state in self.jobs_root.glob("*/job.json"):
            try:
                jobs.append(json.loads(state.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return sorted(jobs, key=lambda item: item.get("updated_at", ""), reverse=True)

    def public(self, job: dict) -> dict:
        chunks = job.get("chunks", [])
        completed = sum(chunk["status"] == "completed" for chunk in chunks)
        duration = (job.get("media") or {}).get("duration", 0)
        processed = max((chunk["end"] for chunk in chunks if chunk["status"] == "completed"), default=0)
        return {
            **job,
            "progress": round(100 * completed / len(chunks), 1) if chunks else 0,
            "completed_chunks": completed,
            "total_chunks": len(chunks),
            "processed_seconds": min(processed, duration),
        }
