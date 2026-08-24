from __future__ import annotations

from dataclasses import asdict, dataclass

from .hardware_detector import MachineProfile


@dataclass(frozen=True)
class ModelSelection:
    backend: str
    model: str
    model_repo: str
    reason: str
    quality: str
    device: str
    compute_type: str

    def to_dict(self) -> dict:
        return asdict(self)


MLX_MODELS = {
    "small": "mlx-community/whisper-small-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    "large-v3-4bit": "mlx-community/whisper-large-v3-mlx-4bit",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
}


def select_model(machine: MachineProfile, mode: str = "auto") -> ModelSelection:
    if not machine.supported:
        raise RuntimeError(f"Unsupported operating system: {machine.platform}")

    memory = machine.memory_gb
    if machine.backend == "mlx":
        if mode == "fast":
            name, quality = "small", "fast"
        elif mode == "accurate":
            name, quality = ("large-v3", "accurate") if memory >= 24 else ("large-v3-4bit", "accurate")
        elif memory < 24:
            name, quality = "large-v3-turbo", "balanced"
        else:
            name, quality = "large-v3", "accurate"
        repo, compute_type = MLX_MODELS[name], "float16"
    elif machine.device == "cuda":
        vram = machine.gpu_memory_gb
        if mode == "fast":
            name, quality = ("large-v3-turbo", "fast") if vram >= 6 else ("small", "fast")
        elif mode == "accurate":
            name, quality = ("large-v3", "accurate") if vram >= 6 else ("medium", "accurate")
        else:
            name, quality = ("large-v3-turbo", "balanced") if vram >= 5 else ("small", "fast")
        repo = name
        compute_type = "float16" if vram >= 8 else "int8_float16"
    else:
        if mode == "fast":
            name, quality = "small", "fast"
        elif mode == "accurate":
            name, quality = ("large-v3", "accurate") if memory >= 24 else ("medium", "accurate")
        else:
            name, quality = ("medium", "balanced") if memory >= 16 and machine.cpu_threads >= 8 else ("small", "fast")
        repo, compute_type = name, "int8"

    if machine.backend == "mlx":
        reason = (
            f"Apple Silicon with {memory} GB unified memory; quantized Large-v3 selected for maximum accuracy"
            if name == "large-v3-4bit"
            else f"Apple Silicon with {memory} GB unified memory; optimized Turbo model selected for accuracy"
            if name == "large-v3-turbo" and memory <= 8
            else f"Apple Silicon with {memory} GB unified memory"
        )
    elif machine.device == "cuda":
        reason = f"{machine.gpu_name} with {machine.gpu_memory_gb} GB VRAM"
    else:
        reason = f"CPU mode with {memory} GB RAM and {machine.cpu_threads} threads"

    return ModelSelection(
        backend=machine.backend,
        model=name,
        model_repo=repo,
        reason=reason,
        quality=quality,
        device=machine.device,
        compute_type=compute_type,
    )


def lighter_model(current: str, backend: str = "mlx") -> tuple[str, str] | None:
    fallback = {
        "large-v3": "large-v3-4bit",
        "large-v3-4bit": "large-v3-turbo",
        "large-v3-turbo": "small",
        "medium": "small",
    }.get(current)
    if not fallback:
        return None
    if backend == "mlx":
        return fallback, MLX_MODELS[fallback]
    if fallback == "large-v3-4bit":
        fallback = "large-v3-turbo"
    return fallback, fallback
