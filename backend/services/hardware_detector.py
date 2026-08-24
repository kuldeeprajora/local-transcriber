from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass


def _command(*args: str) -> str | None:
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.SubprocessError):
        return None


@dataclass(frozen=True)
class MachineProfile:
    platform: str
    architecture: str
    chip: str
    memory_gb: int
    backend: str
    device: str
    recommended_profile: str
    ffmpeg_available: bool
    ffmpeg_path: str | None
    supported: bool
    gpu_name: str | None = None
    gpu_memory_gb: int = 0
    cuda_available: bool = False
    cuda_runtime_available: bool = False
    cpu_threads: int = 1

    def to_dict(self) -> dict:
        return asdict(self)


def detect_hardware() -> MachineProfile:
    system = platform.system()
    architecture = platform.machine().lower()
    chip = _command("sysctl", "-n", "machdep.cpu.brand_string") or platform.processor()
    if not chip and system == "Windows":
        chip = _command("powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name")
    chip = chip or "Unknown CPU"
    raw_memory = _command("sysctl", "-n", "hw.memsize")
    if raw_memory and raw_memory.isdigit():
        memory_gb = max(1, round(int(raw_memory) / 1024**3))
    else:
        try:
            import psutil

            memory_gb = max(1, round(psutil.virtual_memory().total / 1024**3))
        except ImportError:
            memory_gb = 0

    apple_silicon = system == "Darwin" and architecture in {"arm64", "aarch64"}
    gpu_name = None
    gpu_memory_gb = 0
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        query = _command(
            nvidia_smi,
            "--query-gpu=name,memory.total",
            "--format=csv,noheader,nounits",
        )
        candidates = []
        for line in (query or "").splitlines():
            try:
                name, memory_mb = line.rsplit(",", 1)
                candidates.append((round(int(memory_mb.strip()) / 1024), name.strip()))
            except (ValueError, TypeError):
                continue
        if candidates:
            gpu_memory_gb, gpu_name = max(candidates)

    cuda_available = gpu_name is not None
    cuda_runtime_available = False
    if cuda_available:
        try:
            import ctranslate2

            cuda_runtime_available = ctranslate2.get_cuda_device_count() > 0
        except (ImportError, RuntimeError, OSError):
            pass

    cpu_threads = max(1, os.cpu_count() or 1)
    if apple_silicon:
        backend, device = "mlx", "apple_silicon"
        profile = "accurate" if memory_gb >= 24 else "balanced"
    elif cuda_available and cuda_runtime_available:
        backend, device = "faster-whisper", "cuda"
        profile = "accurate" if gpu_memory_gb >= 10 else "balanced" if gpu_memory_gb >= 6 else "fast"
    else:
        backend, device = "faster-whisper", "cpu"
        profile = "balanced" if memory_gb >= 16 and cpu_threads >= 8 else "fast"

    ffmpeg_path = shutil.which("ffmpeg")
    return MachineProfile(
        platform="macOS" if system == "Darwin" else system,
        architecture=architecture,
        chip=chip,
        memory_gb=memory_gb,
        backend=backend,
        device=device,
        recommended_profile=profile,
        ffmpeg_available=ffmpeg_path is not None and shutil.which("ffprobe") is not None,
        ffmpeg_path=ffmpeg_path,
        supported=system in {"Darwin", "Windows", "Linux"},
        gpu_name=gpu_name,
        gpu_memory_gb=gpu_memory_gb,
        cuda_available=cuda_available,
        cuda_runtime_available=cuda_runtime_available,
        cpu_threads=cpu_threads,
    )
