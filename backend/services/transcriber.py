from __future__ import annotations

import gc
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

from .hardware_detector import MachineProfile
from .model_selector import lighter_model

StatusCallback = Callable[[str], None]

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
                status(f"Loading or downloading {model_repo} for {device.upper()}")
            try:
                self._model = WhisperModel(
                    model_repo,
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
