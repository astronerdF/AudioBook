"""Utilities for aligning chapter text to audio using Whisper."""
from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional, Tuple

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
WHISPERX_DEFAULT_BATCH = 16
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


def _resolve_backend_sequence(preferred: Optional[str]) -> List[str]:
    if not preferred or preferred == "auto":
        return ["whisperx", "faster-whisper"]

    normalized = preferred.replace("_", "-").lower()
    if normalized in {"whisperx", "whisper-x"}:
        return ["whisperx"]
    if normalized in {"faster-whisper", "fasterwhisper", "whisper", "faster"}:
        return ["faster-whisper"]

    logger.warning("Unknown alignment backend '%s'; defaulting to auto", preferred)
    return ["whisperx", "faster-whisper"]


def _align_with_whisperx(
    audio_path: str,
    tokens: List[Dict[str, object]],
    language: Optional[str],
    *,
    device: Optional[str],
    model_name: Optional[str],
    compute_type: Optional[str],
    batch_size: Optional[int],
) -> Optional[List[Optional[Dict[str, float]]]]:
    try:  # pragma: no cover - optional dependency
        import torch
        import whisperx  # type: ignore
    except ImportError:
        logger.debug("whisperx not installed; skipping WhisperX alignment")
        return None

    device_type, device_index = _parse_device(device)
    if device_type == "auto":
        device_type = "cuda" if torch.cuda.is_available() else "cpu"
        device_index = 0 if device_type == "cuda" else -1
    elif device_type == "cuda" and not torch.cuda.is_available():
        logger.warning("CUDA requested for WhisperX but no GPU detected; using CPU")
        device_type = "cpu"
        device_index = -1

    resolved_compute = _resolve_compute_type(device_type, compute_type)
    load_kwargs: Dict[str, Any] = {
        "device": device_type,
        "compute_type": resolved_compute,
    }
    if device_index >= 0:
        load_kwargs["device_index"] = device_index

    whisper_model = model_name or "large-v2"

    try:  # pragma: no cover - heavy dependency
        model = whisperx.load_model(whisper_model, **load_kwargs)
    except Exception as exc:
        logger.warning("Failed to load WhisperX model '%s': %s", whisper_model, exc)
        return None

    effective_batch = batch_size if isinstance(batch_size, int) and batch_size > 0 else WHISPERX_DEFAULT_BATCH

    try:
        result = model.transcribe(
            audio_path,
            batch_size=effective_batch,
        )
    except Exception as exc:
        logger.warning("WhisperX transcription failed: %s", exc)
        return None
    finally:
        try:
            del model
        except Exception:  # pragma: no cover - defensive cleanup
            pass

    language_code = result.get("language") or _normalize_language(language) or "en"

    try:
        align_model, metadata = whisperx.load_align_model(
            language_code=language_code,
            device=device_type,
        )
    except Exception as exc:
        logger.warning("Failed to load WhisperX alignment model for '%s': %s", language_code, exc)
        return None

    try:
        aligned = whisperx.align(
            result.get("segments", []),
            align_model,
            metadata,
            audio_path,
            device=device_type,
            return_char_alignments=False,
        )
    except Exception as exc:
        logger.warning("WhisperX forced alignment failed: %s", exc)
        return None
    finally:
        # free heavyweight models ASAP
        try:
            del align_model
        except Exception:  # pragma: no cover - defensive cleanup
            pass

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
        logger.warning("WhisperX did not return any word-level timestamps")
        return None

    return _map_words_to_tokens(tokens, words)


def _align_with_faster_whisper(
    audio_path: str,
    tokens: List[Dict[str, object]],
    language: Optional[str],
    *,
    device: Optional[str],
    model_name: Optional[str],
    compute_type: Optional[str],
) -> Optional[List[Optional[Dict[str, float]]]]:
    if WhisperModel is None:
        logger.warning("faster-whisper not installed; skipping Faster-Whisper alignment")
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


def align_tokens_with_audio(
    audio_path: str,
    tokens: Iterable[Dict[str, object]],
    language: Optional[str],
    *,
    device: Optional[str] = None,
    model_name: Optional[str] = None,
    compute_type: Optional[str] = None,
    backend: Optional[str] = None,
    whisperx_batch_size: Optional[int] = None,
) -> Optional[List[Optional[Dict[str, float]]]]:
    """Align chapter tokens to audio using the requested alignment backend.

    ``backend`` accepts ``"whisperx"``, ``"faster-whisper"`` or ``"auto``.
    When ``auto`` (default) the function tries WhisperX first and falls back to
    the previous Faster-Whisper based alignment if WhisperX is unavailable.
    """

    token_list = list(tokens)
    if not token_list:
        return None

    backend_queue = _resolve_backend_sequence(backend)
    alignment: Optional[List[Optional[Dict[str, float]]]] = None

    for backend_name in backend_queue:
        if backend_name == "whisperx":
            alignment = _align_with_whisperx(
                audio_path,
                token_list,
                language,
                device=device,
                model_name=model_name,
                compute_type=compute_type,
                batch_size=whisperx_batch_size,
            )
        else:
            alignment = _align_with_faster_whisper(
                audio_path,
                token_list,
                language,
                device=device,
                model_name=model_name,
                compute_type=compute_type,
            )

        if alignment and any(entry for entry in alignment if entry):
            logger.info(
                "Using %s backend for timing alignment",
                "WhisperX" if backend_name == "whisperx" else "Faster-Whisper",
            )
            return alignment

        if backend_name == "whisperx" and backend_queue != ["whisperx"]:
            logger.info("WhisperX alignment unavailable; falling back to Faster-Whisper")

    return alignment


__all__ = ["align_tokens_with_audio"]
