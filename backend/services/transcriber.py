from __future__ import annotations

import gc
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

from .hardware_detector import MachineProfile
from .model_selector import lighter_model

StatusCallback = Callable[[str], None]

# Hugging Face reads these values while its module is imported. Configure them
# before either transcription backend imports the Hub client.
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "60")
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "30")

MIXED_LANGUAGE_PROMPT = (
    "नमस्ते। आज हम business, marketing, client, AI, video, content, strategy, "
    "system और implementation के बारे में discuss करेंगे।"
)


def transcription_options(language: str) -> dict:
    options = {
        "word_timestamps": True,
        # Greedy decoding and resetting context at Whisper's internal windows
        # prevent a mistaken phrase from snowballing into repetition loops.
        "temperature": 0.0,
        "condition_on_previous_text": False,
        "hallucination_silence_threshold": 2.0,
        "verbose": False,
    }
    if language in {"en", "hi"}:
        options["language"] = language
    elif language == "hi-en":
        options["language"] = "hi"
        options["initial_prompt"] = MIXED_LANGUAGE_PROMPT
    return options


class TranscriptionError(RuntimeError):
    pass


def _permanent_download_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(term in message for term in (
        "401 client error",
        "403 client error",
        "gated repo",
        "repository not found",
        "no space left",
        "disk full",
        "permission denied",
    ))


def download_faster_whisper_model(
    model_name: str,
    status: StatusCallback | None = None,
    attempts: int = 4,
    download=None,
    sleeper: Callable[[float], None] = time.sleep,
) -> str:
    """Return a complete cached model, resuming transiently interrupted downloads."""
    if download is None:
        try:
            from faster_whisper.utils import download_model
        except ImportError as exc:
            raise TranscriptionError("faster-whisper is not installed. Run the safe installer again.") from exc
        download = download_model

    if status:
        status("Checking the local model cache")
    try:
        return str(download(model_name, local_files_only=True))
    except Exception:
        # A missing or incomplete snapshot is expected on the first run. The
        # network pass below reuses all complete blobs and resumes the rest.
        pass

    last_error: Exception | None = None
    delays = (2, 5, 10)
    for attempt in range(1, attempts + 1):
        if status:
            action = "Downloading model for first use" if attempt == 1 else "Resuming interrupted model download"
            status(f"{action} (attempt {attempt} of {attempts})")
        try:
            return str(download(model_name, local_files_only=False))
        except Exception as exc:
            last_error = exc
            if _permanent_download_error(exc):
                raise TranscriptionError(
                    "The model download cannot continue because access was denied or local storage is unavailable. "
                    "Check disk space, folder permissions, and network access to huggingface.co."
                ) from exc
            if attempt < attempts:
                if status:
                    status(f"Connection interrupted; retrying model download in {delays[attempt - 1]} seconds")
                sleeper(delays[attempt - 1])

    raise TranscriptionError(
        f"The model download was interrupted after {attempts} automatic attempts. The partial download is saved and will "
        "resume instead of starting over. Check the internet connection, VPN, firewall, or antivirus, then click "
        "Retry & resume."
    ) from last_error


class TranscriptionBackend(ABC):
    @abstractmethod
    def transcribe(
        self,
        audio: Path,
        model_repo: str,
        language: str,
        status: StatusCallback | None = None,
        runtime: dict | None = None,
    ) -> dict:
        raise NotImplementedError


class MLXBackend(TranscriptionBackend):
    def transcribe(
        self,
        audio: Path,
        model_repo: str,
        language: str,
        status: StatusCallback | None = None,
        runtime: dict | None = None,
    ) -> dict:
        try:
            import mlx_whisper
        except ImportError as exc:
            raise TranscriptionError(
                "mlx-whisper is not installed. Activate the project environment and run pip install -r requirements.txt."
            ) from exc

        cached = False
        ignore_patterns = ["model.safetensors"] if model_repo.endswith("-mlx-4bit") else None
        try:
            from huggingface_hub import snapshot_download

            model_path = snapshot_download(model_repo, local_files_only=True, ignore_patterns=ignore_patterns)
            cached = True
        except Exception:
            model_path = model_repo
        if status:
            status("Loading cached local model" if cached else "Downloading model for first use…")
        if not cached:
            try:
                from huggingface_hub import snapshot_download

                model_path = snapshot_download(model_repo, ignore_patterns=ignore_patterns)
            except Exception as exc:
                raise TranscriptionError(f"Model download failed: {exc}") from exc
        kwargs = {"path_or_hf_repo": model_path, **transcription_options(language)}
        try:
            result = mlx_whisper.transcribe(str(audio), **kwargs)
        except Exception as exc:  # library raises backend-specific runtime errors
            if not cached and any(term in str(exc).lower() for term in ("download", "connection", "huggingface", "repository")):
                raise TranscriptionError(f"Model download failed: {exc}") from exc
            raise TranscriptionError(str(exc) or exc.__class__.__name__) from exc
        return normalize_result(result)


class FasterWhisperBackend(TranscriptionBackend):
    def __init__(self, device: str, compute_type: str, cpu_threads: int):
        self.device = device
        self.compute_type = compute_type
        self.cpu_threads = cpu_threads
        self._model = None
        self._model_name = None

    def transcribe(
        self,
        audio: Path,
        model_repo: str,
        language: str,
        status: StatusCallback | None = None,
        runtime: dict | None = None,
    ) -> dict:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise TranscriptionError(
                "faster-whisper is not installed. Run pip install -r requirements.txt in the project environment."
            ) from exc

        runtime = runtime or {}
        device = runtime.get("device", self.device)
        compute_type = runtime.get("compute_type", self.compute_type)
        model_key = (model_repo, device, compute_type)
        if self._model is None or self._model_name != model_key:
            self._model = None
            self._model_name = None
            gc.collect()
            if status:
                status(f"Preparing {model_repo} for {device.upper()}")
            model_path = download_faster_whisper_model(model_repo, status=status)
            try:
                self._model = WhisperModel(
                    model_path,
                    device=device,
                    compute_type=compute_type,
                    cpu_threads=self.cpu_threads,
                    download_root=None,
                )
            except Exception as exc:
                message = str(exc)
                if device == "cuda" and any(term in message.lower() for term in ("cublas", "cudnn", "cuda")):
                    raise TranscriptionError(
                        "NVIDIA GPU was detected but CUDA initialization failed. Install CUDA 12 and cuDNN 9, then restart the app. "
                        f"Technical detail: {message}"
                    ) from exc
                raise TranscriptionError(f"Could not load faster-whisper model: {message}") from exc
            self._model_name = model_key

        if status:
            status(f"Transcribing locally with {device.upper()} ({compute_type})")
        transcribe_options = {
            "task": "transcribe",
            "word_timestamps": True,
            "beam_size": 5,
            "patience": 1.0,
            "condition_on_previous_text": False,
            "vad_filter": True,
            "vad_parameters": {"min_silence_duration_ms": 500},
        }
        if language in {"en", "hi"}:
            transcribe_options["language"] = language
        elif language == "hi-en":
            transcribe_options["language"] = "hi"
            transcribe_options["initial_prompt"] = MIXED_LANGUAGE_PROMPT
        try:
            segments, info = self._model.transcribe(str(audio), **transcribe_options)
            normalized = []
            for segment in segments:
                normalized.append({
                    "start": float(segment.start),
                    "end": float(segment.end),
                    "text": str(segment.text).strip(),
                    "words": [
                        {
                            "word": str(word.word),
                            "start": float(word.start or segment.start),
                            "end": float(word.end or segment.end),
                        }
                        for word in (segment.words or [])
                    ],
                })
        except Exception as exc:
            raise TranscriptionError(str(exc) or exc.__class__.__name__) from exc
        return {"language": getattr(info, "language", None), "segments": normalized}


def create_backend(machine: MachineProfile, selection: dict) -> TranscriptionBackend:
    if selection.get("backend") == "mlx":
        return MLXBackend()
    return FasterWhisperBackend(
        device=selection.get("device", machine.device),
        compute_type=selection.get("compute_type", "int8"),
        cpu_threads=machine.cpu_threads,
    )


def normalize_result(result: dict) -> dict:
    segments = []
    for item in result.get("segments", []):
        words = [
            {
                "word": str(word.get("word", "")),
                "start": float(word.get("start", 0)),
                "end": float(word.get("end", 0)),
            }
            for word in item.get("words", [])
        ]
        segments.append({
            "start": float(item.get("start", 0)),
            "end": float(item.get("end", 0)),
            "text": str(item.get("text", "")).strip(),
            "words": words,
        })
    return {"language": result.get("language"), "segments": segments}


def is_memory_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return isinstance(exc, MemoryError) or any(term in message for term in ("out of memory", "memory pressure", "metal heap"))


def release_memory() -> None:
    gc.collect()
    try:
        import mlx.core as mx

        mx.clear_cache()
    except (ImportError, AttributeError):
        pass


def fallback_repo(model_name: str, backend: str = "mlx") -> tuple[str, str] | None:
    return lighter_model(model_name, backend)
