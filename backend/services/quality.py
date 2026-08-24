from __future__ import annotations

from .merger import token_spans


def _tokens(text: str) -> list[str]:
    return [token for token, _, _ in token_spans(text)]


def _longest_run(tokens: list[str]) -> int:
    longest = current = 0
    previous = None
    for token in tokens:
        current = current + 1 if token == previous else 1
        longest = max(longest, current)
        previous = token
    return longest


def analyze_transcript(transcript: dict) -> dict:
    repeated = []
    replacement_characters = 0
    previous_end = 0.0
    long_gaps = []
    for index, segment in enumerate(transcript.get("segments", []), 1):
        text = str(segment.get("text", ""))
        tokens = _tokens(text)
        replacement_characters += text.count("�")
        if len(tokens) >= 10:
            most_common = max((tokens.count(token) for token in set(tokens)), default=0)
            ratio = most_common / len(tokens)
            run = _longest_run(tokens)
            if run >= 5 or ratio >= 0.55:
                repeated.append({
                    "segment": index,
                    "start": float(segment.get("start", 0)),
                    "end": float(segment.get("end", 0)),
                    "repeat_ratio": round(ratio, 2),
                    "longest_run": run,
                    "text": text[:180],
                })
        start = float(segment.get("start", 0))
        if previous_end and start - previous_end >= 30:
            long_gaps.append({"start": previous_end, "end": start, "duration": round(start - previous_end, 2)})
        previous_end = max(previous_end, float(segment.get("end", 0)))

    warnings = []
    if repeated:
        warnings.append(f"{len(repeated)} possible repetition hallucination(s) need review")
    if replacement_characters:
        warnings.append(f"{replacement_characters} invalid text character(s) detected")
    return {
        "status": "review" if warnings else "clean",
        "warnings": warnings,
        "repetition_count": len(repeated),
        "repetitions": repeated,
        "long_gap_count": len(long_gaps),
        "long_gaps": long_gaps,
        "replacement_character_count": replacement_characters,
    }
