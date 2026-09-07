"""Local, conservative music/non-speech detection for transcript navigation."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from .merger import token_spans

FRAME_MS = 30
BLOCK_SECONDS = 3.0
MIN_EVENT_SECONDS = 6.0
INTRO_CHANT_LIMIT_SECONDS = 10 * 60


def _merge_ranges(ranges: list[dict], max_gap: float = 3.0) -> list[dict]:
    merged: list[dict] = []
    for event in ranges:
        if merged and event["start"] <= merged[-1]["end"] + max_gap:
            merged[-1]["end"] = event["end"]
        else:
            merged.append(dict(event))
    return merged


def likely_music_blocks(observations: list[dict]) -> list[dict]:
    """Turn window activity/VAD summaries into conservative music-like ranges.

    Speech usually has a strong VAD ratio. Sustained audible audio with a much
    lower speech ratio is a useful local signal for instrumental music, songs,
    jingles, chanting, and other non-dialogue sections. It intentionally does
    not claim certainty; the visible label says "Music / song (detected)".
    """
    candidates = [
        {"start": float(item["start"]), "end": float(item["end"]), "kind": "music"}
        for item in observations
        if item["active_ratio"] >= 0.70 and item["speech_ratio"] <= 0.55
    ]
    return [event for event in _merge_ranges(candidates) if event["end"] - event["start"] >= MIN_EVENT_SECONDS]


def likely_chant_or_song_segments(transcript: dict) -> list[dict]:
    """Find transcript patterns that are strongly characteristic of sung chants.

    Singing is often detected as human voice by VAD, so audio-only detection
    misses bhajans and songs. A segment with a dominant word repeated many
    times is a high-confidence signal of a chorus/chant or music transcription
    hallucination; either way, a navigation marker is valuable to the user.
    """
    events = []
    for segment in transcript.get("segments", []):
        # Repetition is common in ordinary meetings ("good, good, good"), so
        # only use this text-only signal in the opening where songs, bhajans,
        # and jingles conventionally occur. Audio-only detection remains active
        # throughout the recording.
        if float(segment.get("start", 0)) > INTRO_CHANT_LIMIT_SECONDS:
            continue
        tokens = [token for token, _, _ in token_spans(str(segment.get("text", "")))]
        if len(tokens) < 8:
            continue
        repeats = max((tokens.count(token) for token in set(tokens)), default=0)
        if repeats >= 7 or repeats / len(tokens) >= 0.45:
            events.append({
                "start": float(segment["start"]),
                "end": float(segment["end"]),
                "kind": "music",
            })
    return _merge_ranges(events, max_gap=18.0)


def detect_music(audio: Path) -> list[dict]:
    """Detect likely sustained music/song audio in the extracted 16 kHz WAV.

    The detector runs fully on-device and adds no model download. If the local
    VAD package or WAV format is unavailable, it safely returns no markers.
    """
    try:
        import webrtcvad
        with wave.open(str(audio), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != 16_000:
                return []
            vad = webrtcvad.Vad(2)
            samples_per_frame = 16_000 * FRAME_MS // 1000
            frame_bytes = samples_per_frame * 2
            frames_per_block = max(1, round(BLOCK_SECONDS * 1000 / FRAME_MS))
            observations: list[dict] = []
            block_start = 0.0
            active = speech = frames = 0
            while True:
                frame = wav.readframes(samples_per_frame)
                if len(frame) < frame_bytes:
                    break
                values = struct.unpack(f"<{samples_per_frame}h", frame)
                rms = math.sqrt(sum(value * value for value in values) / samples_per_frame)
                active += rms >= 450  # approximately -37 dBFS; ignores quiet room tone
                speech += vad.is_speech(frame, 16_000)
                frames += 1
                if frames == frames_per_block:
                    end = block_start + frames * FRAME_MS / 1000
                    observations.append({
                        "start": block_start,
                        "end": end,
                        "active_ratio": active / frames,
                        "speech_ratio": speech / frames,
                    })
                    block_start = end
                    active = speech = frames = 0
            if frames:
                end = block_start + frames * FRAME_MS / 1000
                observations.append({
                    "start": block_start,
                    "end": end,
                    "active_ratio": active / frames,
                    "speech_ratio": speech / frames,
                })
    except (ImportError, OSError, wave.Error, struct.error):
        return []
    return likely_music_blocks(observations)


def add_music_markers(transcript: dict, events: list[dict]) -> dict:
    """Insert clearly typed marker segments without discarding spoken text."""
    events = _merge_ranges(sorted(events, key=lambda event: event["start"]), max_gap=18.0)
    markers = [
        {
            "start": event["start"],
            "end": event["end"],
            "text": "[Music / song / chanting — automatically detected]",
            "words": [],
            "kind": "music",
        }
        for event in events
    ]
    return {
        **transcript,
        "music_segments": events,
        "segments": sorted([*transcript.get("segments", []), *markers], key=lambda segment: (segment["start"], segment.get("kind") != "music")),
    }
