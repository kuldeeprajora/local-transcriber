import json
from pathlib import Path

from backend.services.chunker import plan_chunks
from backend.services.exporter import write_exports
from backend.services.hardware_detector import MachineProfile
from backend.services.job_manager import JobManager
from backend.services.merger import merge_chunk_results, remove_prefix_overlap
from backend.services.model_selector import select_model
from backend.services.music_detector import add_music_markers, likely_chant_or_song_segments, likely_music_blocks
from backend.services.transcriber import TranscriptionError, download_faster_whisper_model, transcription_options
from backend.services.quality import analyze_transcript


def machine(memory: int) -> MachineProfile:
    return MachineProfile("macOS", "arm64", "Apple M2", memory, "mlx", "apple_silicon", "balanced", True, "/opt/homebrew/bin/ffmpeg", True)


def windows_cuda(vram: int) -> MachineProfile:
    return MachineProfile(
        "Windows", "amd64", "AMD Ryzen 7", 32, "faster-whisper", "cuda", "balanced", True,
        "C:\\ffmpeg\\bin\\ffmpeg.exe", True, "NVIDIA GeForce RTX", vram, True, True, 16,
    )


def windows_cpu(memory: int, threads: int) -> MachineProfile:
    return MachineProfile(
        "Windows", "amd64", "Intel Core", memory, "faster-whisper", "cpu", "balanced", True,
        "C:\\ffmpeg\\bin\\ffmpeg.exe", True, cpu_threads=threads,
    )


def test_model_selection_profiles():
    assert select_model(machine(8), "auto").model == "large-v3-turbo"
    assert select_model(machine(8), "accurate").model == "large-v3-4bit"
    assert select_model(machine(16), "auto").model == "large-v3-turbo"
    assert select_model(machine(24), "auto").model == "large-v3"
    assert select_model(machine(24), "fast").model == "small"


def test_nvidia_model_and_precision_follow_vram():
    assert select_model(windows_cuda(12), "accurate").model == "large-v3"
    assert select_model(windows_cuda(12), "auto").compute_type == "float16"
    assert select_model(windows_cuda(6), "auto").compute_type == "int8_float16"


def test_windows_cpu_scales_model_to_resources():
    capable = select_model(windows_cpu(32, 16), "auto")
    constrained = select_model(windows_cpu(8, 4), "auto")
    assert (capable.model, capable.compute_type) == ("medium", "int8")
    assert (constrained.model, constrained.compute_type) == ("small", "int8")


def test_model_download_resumes_after_connection_reset():
    calls = []
    statuses = []
    sleeps = []

    def download(name, local_files_only):
        calls.append((name, local_files_only))
        if local_files_only or len(calls) == 2:
            raise ConnectionResetError(10054, "connection forcibly closed")
        return "C:/model-cache/complete-snapshot"

    path = download_faster_whisper_model(
        "large-v3",
        status=statuses.append,
        download=download,
        sleeper=sleeps.append,
    )
    assert path.endswith("complete-snapshot")
    assert calls == [("large-v3", True), ("large-v3", False), ("large-v3", False)]
    assert sleeps == [2]
    assert any("Resuming interrupted" in status for status in statuses)


def test_model_download_failure_is_short_and_actionable():
    def download(_name, local_files_only):
        del local_files_only
        raise ConnectionResetError(10054, "connection forcibly closed")

    try:
        download_faster_whisper_model("large-v3", download=download, sleeper=lambda _seconds: None)
    except TranscriptionError as exc:
        assert "4 automatic attempts" in str(exc)
        assert "Retry & resume" in str(exc)
        assert "cached snapshot" not in str(exc)
    else:
        raise AssertionError("Expected the exhausted download to fail")


def test_mixed_language_decoding_resists_repetition():
    options = transcription_options("hi-en")
    assert options["language"] == "hi"
    assert options["temperature"] == 0.0
    assert options["condition_on_previous_text"] is False
    assert "marketing" in options["initial_prompt"]


def test_chunk_plan_has_three_second_forward_overlap():
    chunks = plan_chunks(1_205)
    assert [(c["start"], c["end"]) for c in chunks] == [(0.0, 603.0), (600.0, 1203.0), (1200.0, 1205.0)]


def test_overlap_deduplication_and_timestamp_offset():
    assert remove_prefix_overlap(
        "aur ab hum next topic ke baare mein",
        "next topic ke baare mein discuss karenge",
    ) == "discuss karenge"
    merged = merge_chunk_results([
        {"chunk_id": 1, "start_offset": 0, "language": "hi", "segments": [{"start": 598, "end": 602, "text": "next topic ke baare mein", "words": []}]},
        {"chunk_id": 2, "start_offset": 600, "language": "hi", "segments": [{"start": 1, "end": 5, "text": "next topic ke baare mein discuss karenge", "words": []}]},
    ])
    assert merged["segments"][1]["text"] == "discuss karenge"
    assert merged["segments"][1]["start"] == 603


def test_devanagari_overlap_keeps_combining_marks_together():
    assert remove_prefix_overlap(
        "अब अपना टारगेट ब्रेकडाउन कर लिया",
        "टारगेट ब्रेकडाउन कर लिया और काम शुरू किया",
    ) == "और काम शुरू किया"


def test_exports(tmp_path: Path):
    transcript = {"language": "en", "segments": [{"start": 4.12, "end": 8.92, "text": "Hello world", "words": []}]}
    job = {"id": "job-1", "filename": "demo.mp4", "media": {"duration": 9}, "model": {"model": "small"}, "language": "auto"}
    exports = write_exports(job, transcript, tmp_path)
    assert (tmp_path / exports["txt"]).read_text() == "Hello world\n"
    assert "00:00:04,120 --> 00:00:08,920" in (tmp_path / exports["srt"]).read_text()
    assert json.loads((tmp_path / exports["json"]).read_text())["segments"][0]["text"] == "Hello world"


def test_music_detection_marks_only_sustained_music_like_audio():
    events = likely_music_blocks([
        {"start": 0, "end": 3, "active_ratio": 0.9, "speech_ratio": 0.1},
        {"start": 3, "end": 6, "active_ratio": 0.9, "speech_ratio": 0.2},
        {"start": 6, "end": 9, "active_ratio": 0.9, "speech_ratio": 0.2},
        {"start": 9, "end": 12, "active_ratio": 0.95, "speech_ratio": 0.9},
    ])
    assert events == [{"start": 0.0, "end": 9.0, "kind": "music"}]

    transcript = add_music_markers(
        {"language": "en", "segments": [{"start": 9, "end": 12, "text": "Welcome", "words": []}]},
        events,
    )
    assert transcript["segments"][0]["kind"] == "music"
    assert transcript["segments"][0]["text"].startswith("[Music / song")
    assert transcript["segments"][1]["text"] == "Welcome"


def test_repetitive_chant_is_marked_when_voice_detection_is_not_enough():
    events = likely_chant_or_song_segments({"segments": [
        {"start": 10, "end": 22, "text": "bhaje hum bhaje hum bhaje hum bhaje hum bhaje hum", "words": []},
        {"start": 30, "end": 35, "text": "Normal spoken explanation starts here", "words": []},
        {"start": 700, "end": 720, "text": "good good good good good good good good", "words": []},
    ]})
    assert events == [{"start": 10.0, "end": 22.0, "kind": "music"}]


def test_retranscription_clone_reuses_local_media(tmp_path: Path):
    manager = JobManager(tmp_path / "jobs")
    original = manager.create("meeting.mp4", "source.mp4")
    paths = manager.paths(original["id"])
    (paths["source"] / "source.mp4").write_bytes(b"media")
    (paths["audio"] / "audio.wav").write_bytes(b"audio")
    original["media"] = {"duration": 10}
    manager.save(original)
    cloned = manager.clone_media(original)
    clone_paths = manager.paths(cloned["id"])
    assert cloned["id"] != original["id"]
    assert (clone_paths["source"] / "source.mp4").read_bytes() == b"media"
    assert (clone_paths["audio"] / "audio.wav").read_bytes() == b"audio"


def test_quality_report_flags_hallucination_loop():
    report = analyze_transcript({"segments": [{
        "start": 10, "end": 20, "text": "तो तो तो तो तो तो तो तो तो तो और फिर"
    }]})
    assert report["status"] == "review"
    assert report["repetition_count"] == 1
