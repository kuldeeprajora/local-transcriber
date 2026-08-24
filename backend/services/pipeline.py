from __future__ import annotations

import json
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .chunker import create_chunk, plan_chunks
from .exporter import write_exports
from .hardware_detector import detect_hardware
from .job_manager import JobManager
from .media import extract_audio, probe_media, require_ffmpeg
from .merger import merge_chunk_results
from .model_selector import select_model
from .quality import analyze_transcript
from .transcriber import TranscriptionError, create_backend, fallback_repo, is_memory_error, release_memory


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


class PipelineRunner:
    """Serial background runner; V1 intentionally processes only one job at a time."""

    def __init__(self, manager: JobManager):
        self.manager = manager
        # Tests and embedders may inject a backend here. Normal runs lazily cache
        # one backend per runtime so a resumed job can move between machines.
        self.backend = None
        self._backends: dict[tuple[str, str, str], object] = {}
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="transcriber")
        self._active: set[str] = set()
        self._guard = threading.Lock()

    def submit(self, job_id: str) -> bool:
        with self._guard:
            if job_id in self._active:
                return False
            self._active.add(job_id)
        self._executor.submit(self._run_safely, job_id)
        return True

    def _run_safely(self, job_id: str) -> None:
        try:
            self.run(job_id)
        except Exception as exc:
            try:
                job = self.manager.load(job_id)
                job["status"] = "FAILED"
                job["stage_detail"] = "Transcription paused. Completed chunks were saved."
                job["error"] = str(exc) or exc.__class__.__name__
                for chunk in job.get("chunks", []):
                    if chunk["status"] == "processing":
                        chunk["status"] = "failed"
                        chunk["error"] = job["error"]
                self.manager.save(job)
            except Exception:
                pass
        finally:
            with self._guard:
                self._active.discard(job_id)

    def run(self, job_id: str) -> None:
        job = self.manager.load(job_id)
        paths = self.manager.paths(job_id)
        source = paths["source"] / job["stored_name"]
        require_ffmpeg()

        if not job.get("media"):
            job.update(status="ANALYZING", stage_detail="Analyzing media", error=None)
            self.manager.save(job)
            job["media"] = probe_media(source)

        audio = paths["audio"] / "audio.wav"
        if not audio.is_file():
            job.update(status="EXTRACTING_AUDIO", stage_detail="Extracting 16 kHz mono audio", error=None)
            self.manager.save(job)
            estimated_bytes = int(job["media"]["duration"] * 16000 * 2)
            if shutil.disk_usage(paths["root"]).free < estimated_bytes + 512 * 1024**2:
                raise RuntimeError("Not enough free disk space to extract and process this recording.")
            extract_audio(source, audio)

        if not job.get("chunks"):
            job.update(status="CHUNKING", stage_detail="Planning 10-minute chunks")
            job["chunks"] = plan_chunks(job["media"]["duration"])
            self.manager.save(job)

        machine = detect_hardware()
        if not job.get("model"):
            job["model"] = select_model(machine, job.get("quality", "auto")).to_dict()
        else:
            # Backward compatibility for jobs created before multi-platform
            # runtime metadata was persisted.
            selected = select_model(machine, job.get("quality", "auto")).to_dict()
            for key in ("backend", "device", "compute_type"):
                job["model"].setdefault(key, selected[key])
        job.update(status="TRANSCRIBING", stage_detail="Preparing local model", error=None)
        for chunk in job["chunks"]:
            if chunk["status"] == "processing":
                chunk["status"] = "waiting"
            if chunk["status"] == "failed":
                chunk["status"] = "waiting"
                chunk["error"] = None
        self.manager.save(job)

        for chunk in job["chunks"]:
            result_path = paths["results"] / chunk["output"]
            if chunk["status"] == "completed" and result_path.is_file():
                continue
            chunk["status"] = "processing"
            chunk["error"] = None
            job["stage_detail"] = f"Transcribing chunk {chunk['chunk_id']} of {len(job['chunks'])}"
            self.manager.save(job)

            chunk_path = paths["chunks"] / chunk["file"]
            if not chunk_path.is_file():
                create_chunk(audio, chunk_path, chunk["start"], chunk["end"])
            result = self._transcribe_with_fallback(job, chunk_path)
            chunk_result = {
                "chunk_id": chunk["chunk_id"],
                "start_offset": chunk["start"],
                "language": result.get("language"),
                "segments": result["segments"],
            }
            _write_json(result_path, chunk_result)
            chunk["status"] = "completed"
            chunk["error"] = None
            self.manager.save(job)

        job.update(status="MERGING", stage_detail="Merging chunks and removing boundary overlap")
        self.manager.save(job)
        results = [
            json.loads((paths["results"] / chunk["output"]).read_text(encoding="utf-8"))
            for chunk in job["chunks"]
        ]
        transcript = merge_chunk_results(results)
        _write_json(paths["results"] / "merged.json", transcript)
        job["quality_report"] = analyze_transcript(transcript)

        job.update(status="EXPORTING", stage_detail="Writing TXT, SRT and JSON exports")
        self.manager.save(job)
        job["exports"] = write_exports(job, transcript, paths["exports"])
        job.update(status="COMPLETED", stage_detail="Transcription complete", error=None)
        self.manager.save(job)

    def _transcribe_with_fallback(self, job: dict, chunk_path: Path) -> dict:
        model_name = job["model"]["model"]
        model_repo = job["model"]["model_repo"]
        backend = self._backend_for(job)
        for attempt in range(2):
            try:
                return backend.transcribe(
                    chunk_path,
                    model_repo,
                    job.get("language", "auto"),
                    lambda detail: self._set_detail(job, detail),
                    runtime=job["model"],
                )
            except TranscriptionError as exc:
                if not is_memory_error(exc):
                    raise
                release_memory()
                if attempt == 0:
                    self._set_detail(job, f"Memory pressure detected; retrying {model_name} once")

        fallback = fallback_repo(model_name, job["model"]["backend"])
        if not fallback:
            raise TranscriptionError("The lightweight model also ran out of available memory.")
        new_name, new_repo = fallback
        job["model_adjustment"] = {
            "from": model_name,
            "to": new_name,
            "reason": "Insufficient available memory",
        }
        job["model"].update(model=new_name, model_repo=new_repo, reason="Adjusted after memory pressure")
        self.manager.save(job)
        release_memory()
        return backend.transcribe(
            chunk_path,
            new_repo,
            job.get("language", "auto"),
            lambda d: self._set_detail(job, d),
            runtime=job["model"],
        )

    def _backend_for(self, job: dict):
        if self.backend is not None:
            return self.backend
        machine = detect_hardware()
        selection = job["model"]
        key = (
            selection.get("backend", machine.backend),
            selection.get("device", machine.device),
            selection.get("compute_type", "int8"),
        )
        if key not in self._backends:
            self._backends[key] = create_backend(machine, selection)
        return self._backends[key]

    def _set_detail(self, job: dict, detail: str) -> None:
        job["stage_detail"] = detail
        self.manager.save(job)

    def resume_interrupted(self) -> None:
        resumable = {"ANALYZING", "EXTRACTING_AUDIO", "CHUNKING", "TRANSCRIBING", "MERGING", "EXPORTING"}
        for job in self.manager.list():
            if job.get("status") in resumable:
                self.submit(job["id"])

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)
