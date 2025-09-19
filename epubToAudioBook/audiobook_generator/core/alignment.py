"""Utilities for aligning chapter text to audio using Whisper."""
from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    from faster_whisper import WhisperModel  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    WhisperModel = None  # type: ignore


LANGUAGE_MAP = {
    "en": "en",
    "en-us": "en",
    "en_gb": "en",
    "en-uk": "en",
    "en-gb": "en",
}

MODEL_CACHE: Dict[Tuple[str, int, str, str], WhisperModel] = {}
TOKEN_NORMALIZER = re.compile(r"[^0-9a-z]+", re.IGNORECASE)


def _normalize_language(language: Optional[str]) -> Optional[str]:
    if not language:
        return None
    key = language.replace(" ", "").replace("_", "-").lower()
    if key in LANGUAGE_MAP:
        return LANGUAGE_MAP[key]
    return key[:2]


def _normalize_token(token: str) -> str:
    return TOKEN_NORMALIZER.sub("", token.lower())


def _parse_device(device: Optional[str]) -> Tuple[str, int]:
    if not device or device == "auto":
        return "auto", -1
    if device.startswith("cuda"):
        if ":" in device:
            try:
                index = int(device.split(":", 1)[1])
            except ValueError:
                index = 0
        else:
            index = 0
        return "cuda", index
    return device, -1


def _resolve_compute_type(device: str, requested: Optional[str]) -> str:
    if requested:
        return requested
    if device == "cuda":
        return "float16"
    return "int8_float16"


def _load_whisper_model(
    device: Optional[str],
    model_name: str,
    compute_type: Optional[str],
) -> WhisperModel:
    if WhisperModel is None:
        raise ImportError("faster-whisper is not installed")

    device_type, device_index = _parse_device(device)
    resolved_compute = _resolve_compute_type(device_type, compute_type)
    cache_key = (device_type, device_index, model_name, resolved_compute)

    model = MODEL_CACHE.get(cache_key)
    if model is not None:
        return model

    kwargs = {
        "device": device_type,
        "compute_type": resolved_compute,
    }
    if device_index >= 0:
        kwargs["device_index"] = device_index

    logger.info(
        "Loading Whisper model '%s' for alignment (device=%s, index=%s, compute_type=%s)",
        model_name,
        device_type,
        "auto" if device_index < 0 else device_index,
        resolved_compute,
    )

    model = WhisperModel(model_name, **kwargs)  # type: ignore[arg-type]
    MODEL_CACHE[cache_key] = model
    return model


def _flatten_words(segments) -> List[Dict[str, float]]:
    words: List[Dict[str, float]] = []
    for segment in segments:
        segment_start = float(getattr(segment, "start", 0.0) or 0.0)
        segment_end = float(getattr(segment, "end", segment_start) or segment_start)
        segment_words = getattr(segment, "words", None)
        if segment_words:
            for word in segment_words:
                raw = getattr(word, "word", "") or ""
                text = raw.strip()
                if not text:
                    continue
                start = getattr(word, "start", None)
                end = getattr(word, "end", None)
                word_start = float(start if start is not None else segment_start)
                word_end = float(end if end is not None else segment_end)
                words.append({
                    "text": text,
                    "start": max(0.0, word_start),
                    "end": max(word_start, word_end),
                })
        else:
            text = (getattr(segment, "text", "") or "").strip()
            if not text:
                continue
            words.append({
                "text": text,
                "start": segment_start,
                "end": segment_end,
            })
    return words


def _assign_span(
    token_entries: List[Tuple[int, str]],
    word_entries: List[Dict[str, float]],
    assignments: Dict[int, Dict[str, float]],
) -> None:
    if not token_entries or not word_entries:
        return

    span_start = word_entries[0]["start"]
    span_end = word_entries[-1]["end"]
    span_end = max(span_start, span_end)
    span_duration = max(0.0, span_end - span_start)

    count = len(token_entries)
    for idx, (token_index, _) in enumerate(token_entries):
        if span_duration == 0.0:
            token_start = span_start
            token_end = span_end
        else:
            frac_start = idx / count
            frac_end = (idx + 1) / count
            token_start = span_start + span_duration * frac_start
            token_end = span_start + span_duration * frac_end
        assignments[token_index] = {
            "start": token_start,
            "end": max(token_start, token_end),
        }


def _map_words_to_tokens(
    tokens: List[Dict[str, object]],
    words: List[Dict[str, float]],
) -> List[Optional[Dict[str, float]]]:
    token_word_entries: List[Tuple[int, str]] = []
    for idx, token in enumerate(tokens):
        value = str(token.get("value", ""))
        if re.search(r"\w", value):
            normalized = _normalize_token(value)
            if normalized:
                token_word_entries.append((idx, normalized))

    whisper_entries: List[Tuple[str, Dict[str, float]]] = []
    for word in words:
        normalized = _normalize_token(word["text"])
        if normalized:
            whisper_entries.append((normalized, word))

    if not token_word_entries or not whisper_entries:
        return [None] * len(tokens)

    matcher = SequenceMatcher(
        None,
        [entry[1] for entry in token_word_entries],
        [entry[0] for entry in whisper_entries],
        autojunk=False,
    )

    assignments: Dict[int, Dict[str, float]] = {}
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                token_index = token_word_entries[i1 + offset][0]
                word_info = whisper_entries[j1 + offset][1]
                assignments[token_index] = {
                    "start": word_info["start"],
                    "end": word_info["end"],
                }
        else:
            token_slice = token_word_entries[i1:i2]
            word_slice = [entry[1] for entry in whisper_entries[j1:j2]]
            _assign_span(token_slice, word_slice, assignments)

    results: List[Optional[Dict[str, float]]] = [None] * len(tokens)
    last_end = 0.0
    for idx in range(len(tokens)):
        aligned = assignments.get(idx)
        if not aligned:
            results[idx] = None
            continue
        start = max(last_end, aligned["start"])
        end = max(start, aligned["end"])
        results[idx] = {"start": start, "end": end}
        last_end = end

    return results


def align_tokens_with_audio(
    audio_path: str,
    tokens: Iterable[Dict[str, object]],
    language: Optional[str],
    *,
    device: Optional[str] = None,
    model_name: Optional[str] = None,
    compute_type: Optional[str] = None,
) -> Optional[List[Optional[Dict[str, float]]]]:
    """Align chapter tokens to audio using a Whisper-based aligner.

    Returns a list matching ``tokens`` containing timing dictionaries with
    ``start``/``end`` in seconds for aligned tokens. Entries may be ``None``
    when a token could not be aligned. ``None`` is returned when alignment
    completely fails and the caller should fallback to heuristics.
    """

    tokens = list(tokens)
    if not tokens:
        return None

    if WhisperModel is None:
        logger.warning("faster-whisper not installed; falling back to heuristic timings")
        return None

    selected_model = model_name or "medium.en"

    try:
        model = _load_whisper_model(device, selected_model, compute_type)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to load Whisper model '%s': %s", selected_model, exc)
        return None

    whisper_language = _normalize_language(language)

    try:
        segments, _info = model.transcribe(  # type: ignore[attr-defined]
            audio_path,
            language=whisper_language,
            beam_size=5,
            word_timestamps=True,
            vad_filter=True,
        )
        segment_list = list(segments)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Whisper transcription failed: %s", exc)
        return None

    words = _flatten_words(segment_list)
    if not words:
        logger.warning("Whisper did not return any word-level timestamps")
        return None

    return _map_words_to_tokens(tokens, words)


__all__ = ["align_tokens_with_audio"]
