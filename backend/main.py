from __future__ import annotations

import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .models.schemas import RetryRequest, StartJobRequest
from .services.hardware_detector import detect_hardware
from .services.job_manager import JobManager
from .services.media import SUPPORTED_EXTENSIONS, MediaError, probe_media
from .services.model_selector import select_model
from .services.pipeline import PipelineRunner

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
JOBS_ROOT = ROOT / "data" / "jobs"
manager = JobManager(JOBS_ROOT)
runner = PipelineRunner(manager)


def dependency_status(machine) -> dict:
    required = "mlx_whisper" if machine.backend == "mlx" else "faster_whisper"
    installed = importlib.util.find_spec(required) is not None
    return {
        "required": required,
        "ready": installed,
        "mlx_whisper": importlib.util.find_spec("mlx_whisper") is not None,
        "faster_whisper": importlib.util.find_spec("faster_whisper") is not None,
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    runner.resume_interrupted()
    yield
    runner.shutdown()


app = FastAPI(title="Local Transcriber", version="0.1.0", lifespan=lifespan)


def get_job(job_id: str) -> dict:
    try:
        return manager.load(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "Job not found") from exc


@app.get("/api/health")
def health() -> dict:
    machine = detect_hardware()
    dependencies = dependency_status(machine)
    return {"ok": machine.supported and machine.ffmpeg_available and dependencies["ready"]}


@app.get("/api/system")
def system_info() -> dict:
    machine = detect_hardware()
    selections = {}
    if machine.supported:
        selections = {mode: select_model(machine, mode).to_dict() for mode in ("auto", "accurate", "fast")}
    return {
        "machine": machine.to_dict(),
        "selections": selections,
        "dependencies": dependency_status(machine),
    }


@app.get("/api/jobs")
def list_jobs() -> list[dict]:
    return [manager.public(job) for job in manager.list()]


@app.post("/api/jobs")
async def create_job(
    file: UploadFile = File(...),
    language: str = Form("auto"),
    quality: str = Form("auto"),
) -> dict:
    extension = Path(file.filename or "").suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
    if language not in {"auto", "en", "hi", "hi-en"} or quality not in {"auto", "accurate", "fast"}:
        raise HTTPException(400, "Invalid language or quality mode")
    stored_name = f"source{extension}"
    job = manager.create(Path(file.filename or stored_name).name, stored_name)
    destination = manager.paths(job["id"])["source"] / stored_name
    try:
        with destination.open("wb") as output:
            while block := await file.read(1024 * 1024):
                output.write(block)
        job.update(status="ANALYZING", stage_detail="Analyzing media", language=language, quality=quality)
        manager.save(job)
        job["media"] = probe_media(destination)
        machine = detect_hardware()
        if not machine.supported:
            raise MediaError("This operating system is not supported. Use macOS, Windows, or Linux.")
        if not machine.ffmpeg_available:
            raise MediaError("FFmpeg and FFprobe are required. Install FFmpeg, then restart the app.")
        dependencies = dependency_status(machine)
        if not dependencies["ready"]:
            raise MediaError(f"{dependencies['required'].replace('_', '-')} is missing. Install the project requirements.")
        job["model"] = select_model(machine, quality).to_dict()
        job.update(status="CREATED", stage_detail="Ready to transcribe")
        manager.save(job)
        return manager.public(job)
    except Exception as exc:
        job.update(status="FAILED", stage_detail="Media import failed", error=str(exc))
        manager.save(job)
        raise HTTPException(400, str(exc)) from exc
    finally:
        await file.close()


@app.post("/api/jobs/{job_id}/start")
def start_job(job_id: str, request: StartJobRequest) -> dict:
    job = get_job(job_id)
    if job["status"] not in {"CREATED", "FAILED"}:
        raise HTTPException(409, f"Job cannot start while status is {job['status']}")
    machine = detect_hardware()
    job.update(
        language=request.language,
        quality=request.quality,
        model=select_model(machine, request.quality).to_dict(),
        status="EXTRACTING_AUDIO",
        stage_detail="Queued for local processing",
        error=None,
    )
    for chunk in job.get("chunks", []):
        if chunk["status"] == "failed":
            chunk.update(status="waiting", error=None)
    manager.save(job)
    runner.submit(job_id)
    return manager.public(job)


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    return manager.public(get_job(job_id))


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: str, request: RetryRequest) -> dict:
    job = get_job(job_id)
    if job["status"] != "FAILED":
        raise HTTPException(409, "Only a failed job can be retried")
    if request.chunk_id is not None:
        target = next((c for c in job.get("chunks", []) if c["chunk_id"] == request.chunk_id), None)
        if not target:
            raise HTTPException(404, "Chunk not found")
        target.update(status="waiting", error=None)
    job.update(status="TRANSCRIBING", stage_detail="Queued to resume", error=None)
    manager.save(job)
    runner.submit(job_id)
    return manager.public(job)


@app.post("/api/jobs/{job_id}/retranscribe")
def retranscribe_job(job_id: str, request: StartJobRequest) -> dict:
    source_job = get_job(job_id)
    if not source_job.get("media"):
        raise HTTPException(409, "The original media is not ready for re-transcription")
    machine = detect_hardware()
    job = manager.clone_media(source_job)
    job.update(
        language=request.language,
        quality=request.quality,
        model=select_model(machine, request.quality).to_dict(),
        status="EXTRACTING_AUDIO",
        stage_detail="Queued for higher-accuracy transcription",
        error=None,
    )
    manager.save(job)
    runner.submit(job["id"])
    return manager.public(job)


@app.get("/api/jobs/{job_id}/transcript")
def transcript(job_id: str) -> dict:
    job = get_job(job_id)
    path = manager.paths(job_id)["results"] / "merged.json"
    if not path.is_file():
        raise HTTPException(404, "Transcript is not ready")
    import json

    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/jobs/{job_id}/exports/{kind}")
def download_export(job_id: str, kind: str):
    job = get_job(job_id)
    if kind not in {"txt", "srt", "json"} or kind not in job.get("exports", {}):
        raise HTTPException(404, "Export is not ready")
    path = manager.paths(job_id)["exports"] / job["exports"][kind]
    return FileResponse(path, filename=f"{Path(job['filename']).stem}-transcript.{kind}")


app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
