from __future__ import annotations

import unicodedata

from .chunker import OVERLAP_SECONDS


def _is_token_character(character: str) -> bool:
    # Devanagari vowel signs and viramas are Unicode marks, not ``\w``.
    return character in {"'", "’"} or unicodedata.category(character)[0] in {"L", "M", "N"}


def token_spans(text: str) -> list[tuple[str, int, int]]:
    spans: list[tuple[str, int, int]] = []
    start: int | None = None
    for index, character in enumerate(text):
        if _is_token_character(character):
            if start is None:
                start = index
        elif start is not None:
            spans.append((text[start:index].casefold(), start, index))
            start = None
    if start is not None:
        spans.append((text[start:].casefold(), start, len(text)))
    return spans


def overlap_word_count(previous: str, current: str, minimum_words: int = 2) -> int:
    before = [token for token, _, _ in token_spans(previous)]
    after = [token for token, _, _ in token_spans(current)]
    for size in range(min(len(before), len(after), 60), minimum_words - 1, -1):
        if before[-size:] == after[:size]:
            return size
    return 0


def remove_prefix_overlap(previous: str, current: str, minimum_words: int = 2) -> str:
    """Remove the longest Unicode word suffix/prefix match."""
    match_size = overlap_word_count(previous, current, minimum_words)
    if not match_size:
        return current.strip()
    spans = token_spans(current)
    return current[spans[match_size - 1][2]:].lstrip(" ,.-–—।").strip()


def _global_words(segment: dict, offset: float) -> list[dict]:
    return [
        {
            **word,
            "start": offset + float(word.get("start", 0)),
            "end": offset + float(word.get("end", 0)),
        }
        for word in segment.get("words", [])
    ]


def _trim_chunk_overlap(segment: dict, offset: float, cutoff: float) -> tuple[str, float, list[dict]] | None:
    """Keep the earlier chunk as source of truth inside the overlap interval."""
    text = segment.get("text", "").strip()
    start = offset + float(segment.get("start", 0))
    end = offset + float(segment.get("end", 0))
    words = _global_words(segment, offset)
    if end <= cutoff:
        return None
    if start < cutoff and words:
        words = [word for word in words if word["end"] > cutoff]
        if not words:
            return None
        reconstructed = "".join(str(word.get("word", "")) for word in words).strip()
        if reconstructed:
            text = reconstructed
        start = max(cutoff, words[0]["start"])
    elif start < cutoff:
        start = cutoff
    return text, start, words


def merge_chunk_results(results: list[dict], overlap_seconds: float = OVERLAP_SECONDS) -> dict:
    merged: list[dict] = []
    language = None
    ordered = sorted(results, key=lambda value: value["chunk_id"])
    for result_index, result in enumerate(ordered):
        offset = float(result["start_offset"])
        cutoff = offset + overlap_seconds if result_index else offset
        language = language or result.get("language")
        boundary_tail = " ".join(item["text"] for item in merged if item["end"] >= offset - 15)
        boundary_open = result_index > 0
        for segment in result.get("segments", []):
            trimmed = _trim_chunk_overlap(segment, offset, cutoff) if result_index else (
                segment.get("text", "").strip(),
                offset + float(segment.get("start", 0)),
                _global_words(segment, offset),
            )
            if not trimmed:
                continue
            text, global_start, words = trimmed
            global_end = offset + float(segment.get("end", 0))
            if not text:
                continue
            # Secondary textual deduplication applies only at a chunk boundary.
            if boundary_open and boundary_tail:
                match_size = overlap_word_count(boundary_tail, text)
                text = remove_prefix_overlap(boundary_tail, text)
                if match_size and words:
                    words = words[match_size:]
                    if words:
                        global_start = max(global_start, words[0]["start"])
                if not text:
                    continue
                boundary_open = False
            merged.append({"start": global_start, "end": global_end, "text": text, "words": words})
            if global_start > cutoff + 8:
                boundary_open = False
    return {"language": language, "segments": merged}
