"""Utilities for aligning chapter text to audio using selectable backends."""
from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

SUPPORTED_ALIGNERS = {"whisperx", "nemo", "torchaudio"}

LANGUAGE_MAP = {
    "en": "en",
    "en-us": "en",
    "en_gb": "en",
    "en-uk": "en",
    "en-gb": "en",
}

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


def _resolve_device_hint(device_hint: Optional[str]) -> str:
    if device_hint:
        return device_hint
    try:  # pragma: no cover - torch is optional at runtime
        import torch

        if torch.cuda.is_available():
            return "cuda"
    except Exception:  # pragma: no cover - optional dependency
        pass
    return "cpu"


def _assign_span(
    token_entries: List[tuple[int, str]],
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
    token_word_entries: List[tuple[int, str]] = []
    for idx, token in enumerate(tokens):
        value = str(token.get("value", ""))
        if re.search(r"\w", value):
            normalized = _normalize_token(value)
            if normalized:
                token_word_entries.append((idx, normalized))

    whisper_entries: List[tuple[str, Dict[str, float]]] = []
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


def _align_with_whisperx(
    audio_path: str,
    tokens: List[Dict[str, object]],
    language: Optional[str],
    device: Optional[str],
    model_name: Optional[str],
    batch_size: Optional[int],
) -> Optional[List[Optional[Dict[str, float]]]]:
    try:  # pragma: no cover - optional dependency
        import whisperx
    except ImportError:  # pragma: no cover - optional dependency
        logger.warning("WhisperX is not installed; unable to run alignment.")
        return None

    resolved_device = _resolve_device_hint(device)
    model_id = model_name or "large-v2"
    language_hint = _normalize_language(language)

    try:
        asr_model = whisperx.load_model(model_id, device=resolved_device)
        result = asr_model.transcribe(
            audio_path,
            batch_size=batch_size or 16,
            language=language_hint,
        )
        detected_language = result.get("language") or language_hint or "en"
        align_model, metadata = whisperx.load_align_model(
            language=detected_language,
            device=resolved_device,
        )
        aligned = whisperx.align(
            result["segments"],
            align_model,
            metadata,
            audio_path,
            device=resolved_device,
            return_char_alignments=False,
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("WhisperX alignment failed: %s", exc)
        return None

    words: List[Dict[str, float]] = []
    for segment in aligned.get("segments", []):
        for word in segment.get("words", []):
            text = (word.get("word") or "").strip()
            if not text:
                continue
            start = word.get("start")
            end = word.get("end")
            if start is None or end is None:
                continue
            words.append({
                "text": text,
                "start": float(start),
                "end": float(end),
            })

    if not words:
        logger.warning("WhisperX returned no word-level timestamps.")
        return None

    return _map_words_to_tokens(tokens, words)


def _align_with_nemo(
    audio_path: str,
    tokens: List[Dict[str, object]],
    language: Optional[str],
    device: Optional[str],
    model_name: Optional[str],
) -> Optional[List[Optional[Dict[str, float]]]]:
    try:  # pragma: no cover - optional dependency
        import nemo.collections.asr as nemo_asr
    except ImportError:  # pragma: no cover - optional dependency
        logger.warning("NVIDIA NeMo is not installed; unable to run forced alignment.")
        return None

    logger.warning(
        "NVIDIA NeMo forced alignment backend is not yet implemented in this build."
        " Please integrate nemo.collections.asr.models.NemoForcedAligner and rerun."
    )
    return None


def _align_with_torchaudio(
    audio_path: str,
    tokens: List[Dict[str, object]],
    language: Optional[str],
    device: Optional[str],
    model_name: Optional[str],
) -> Optional[List[Optional[Dict[str, float]]]]:
    try:  # pragma: no cover - optional dependency
        import torchaudio  # noqa: F401
    except ImportError:  # pragma: no cover - optional dependency
        logger.warning("torchaudio is not installed; unable to run forced alignment.")
        return None

    logger.warning(
        "torchaudio CTC forced alignment backend is not yet implemented in this build."
        " Please integrate torchaudio.functional.forced_align and rerun."
    )
    return None


def align_tokens_with_audio(
    audio_path: str,
    tokens: Iterable[Dict[str, object]],
    language: Optional[str],
    *,
    backend: Optional[str] = None,
    device: Optional[str] = None,
    model_name: Optional[str] = None,
    batch_size: Optional[int] = None,
) -> Optional[List[Optional[Dict[str, float]]]]:
    """Align chapter tokens to audio using the requested backend.

    Returns a list matching ``tokens`` containing dictionaries with ``start``/``end``
    (seconds). ``None`` is returned when alignment fails for every token.
    """

    token_list = list(tokens)
    if not token_list:
        return None

    backend_key = (backend or "whisperx").lower()
    if backend_key not in SUPPORTED_ALIGNERS:
        logger.warning("Unsupported alignment backend '%s'", backend_key)
        return None

    if backend_key == "whisperx":
        return _align_with_whisperx(audio_path, token_list, language, device, model_name, batch_size)

    if backend_key == "nemo":
        return _align_with_nemo(audio_path, token_list, language, device, model_name)

    if backend_key == "torchaudio":
        return _align_with_torchaudio(audio_path, token_list, language, device, model_name)

    return None


__all__ = ["align_tokens_with_audio", "SUPPORTED_ALIGNERS"]
