import json
import logging
import os
import re
import tempfile
from typing import Dict, List

import numpy as np
import soundfile as sf

from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.core.alignment import align_tokens_with_audio
from audiobook_generator.tts_providers.base_tts_provider import BaseTTSProvider
from audiobook_generator.utils.utils import split_text, set_audio_tags, pydub_merge_audio_segments

logger = logging.getLogger(__name__)

TOKEN_PATTERN = re.compile(r"[\w]+(?:['\-][\w]+)*|[^\s]", re.UNICODE)
PAUSE_TOKENS = {".", "!", "?", ";", ":"}
MIN_TOKEN_WEIGHT = 3


class KokoroTTSProvider(BaseTTSProvider):
    def __init__(self, config):
        super().__init__(config)
        # kokoro tts specific initialization
        self.device = self.config.device or "cpu"
        self.tts_model = None

    def validate_config(self):
        if not getattr(self.config, "voice_name", None):
            self.config.voice_name = "af_heart"
        if not getattr(self.config, "language", None):
            self.config.language = "en-US"

    def get_tts_model(self):
        if self.tts_model is None:
            from kokoro_tts import KokoroTTS
            # language selection currently limited to English voices (lang_code='a')
            self.tts_model = KokoroTTS(repo_id='hexgrad/Kokoro-82M', device=self.device)
        return self.tts_model

    def get_break_string(self):
        return ""

    def get_output_file_extension(self):
        return "wav"

    def text_to_speech(self, text: str, output_file: str, audio_tags: AudioTags):
        chunk_size = getattr(self.config, "kokoro_chunk_chars", None)
        max_chars = chunk_size if chunk_size and chunk_size > 0 else 3000  # Adjust as needed
        text_chunks = split_text(text, max_chars, self.config.language)

        chunk_records: List[Dict] = []
        all_tokens: List[Dict] = []
        temp_files: List[str] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            running_char_offset = 0

            for i, chunk in enumerate(text_chunks):
                chunk_id = f"chapter-{audio_tags.idx}_{audio_tags.title}_chunk_{i}_of_{len(text_chunks)}"
                logger.info("Processing %s, length=%s", chunk_id, len(chunk))

                temp_file = os.path.join(temp_dir, f"{i}.wav")
                audio_stats = self._synthesize_speech(chunk, temp_file)

                temp_files.append(temp_file)
                chunk_records.append(
                    {
                        "text": chunk,
                        "audio_path": temp_file,
                        "duration": audio_stats["duration"],
                        "leading_silence": audio_stats["leading_silence"],
                        "trailing_silence": audio_stats["trailing_silence"],
                        "char_offset": running_char_offset,
                    }
                )

                tokens = list(self._tokenize(chunk, running_char_offset))
                all_tokens.extend(tokens)

                running_char_offset += len(chunk)

            pydub_merge_audio_segments(temp_files, output_file, self.get_output_file_extension())

        try:
            set_audio_tags(output_file, audio_tags)
        except ValueError as exc:
            logger.warning("Skipping metadata tags for %s: %s", output_file, exc)

        if getattr(self.config, "emit_timestamps", True):
            timings = self._build_precise_timings(output_file, chunk_records, all_tokens)
            total_duration_ms = int(sum(record["duration"] for record in chunk_records) * 1000)
            self._write_metadata(output_file, audio_tags, text, timings, total_duration_ms)

    def _synthesize_speech(self, text: str, output_file: str) -> Dict[str, float]:
        self.get_tts_model().synthesize(
            text=text,
            output_file=output_file,
            voice=self.config.voice_name,
            language="en",
        )
        return self._analyze_audio(output_file)

    def _analyze_audio(self, audio_path: str) -> Dict[str, float]:
        with sf.SoundFile(audio_path) as audio_file:
            sample_rate = audio_file.samplerate or 1
            frames = audio_file.frames
            audio_file.seek(0)
            data = audio_file.read(dtype="float32")

        if data.size == 0 or frames == 0:
            return {"duration": 0.0, "leading_silence": 0.0, "trailing_silence": 0.0}

        if data.ndim > 1:
            amplitudes = np.max(np.abs(data), axis=1)
        else:
            amplitudes = np.abs(data)

        max_amplitude = float(np.max(amplitudes)) if amplitudes.size else 0.0
        if max_amplitude <= 1e-6:
            duration = frames / sample_rate
            return {"duration": duration, "leading_silence": 0.0, "trailing_silence": 0.0}

        adaptive_threshold = max(1e-4, max_amplitude * 0.005)
        non_silent_indices = np.nonzero(amplitudes >= adaptive_threshold)[0]

        if non_silent_indices.size == 0:
            duration = frames / sample_rate
            return {"duration": duration, "leading_silence": 0.0, "trailing_silence": duration}

        first_non_silent = int(non_silent_indices[0])
        last_non_silent = int(non_silent_indices[-1])

        leading_silence = max(0.0, first_non_silent / sample_rate)
        trailing_silence = max(0.0, (frames - last_non_silent - 1) / sample_rate)
        duration = frames / sample_rate

        return {
            "duration": duration,
            "leading_silence": leading_silence,
            "trailing_silence": trailing_silence,
        }

    def _build_precise_timings(
        self,
        audio_path: str,
        chunk_records: List[Dict],
        tokens: List[Dict],
    ) -> List[Dict]:
        timings = self._build_word_timings_estimate(chunk_records, tokens)

        alignment = align_tokens_with_audio(
            audio_path,
            tokens,
            getattr(self.config, "language", "en"),
            device=getattr(self.config, "device", None),
            model_name=getattr(self.config, "kokoro_alignment_model", None),
            compute_type=getattr(self.config, "kokoro_alignment_compute_type", None),
        )

        if alignment and any(entry for entry in alignment if entry):
            logger.info("Using Whisper forced alignment for timings")
            for idx, aligned in enumerate(alignment):
                if not aligned:
                    continue
                start_ms = int(aligned["start"] * 1000)
                end_ms = int(aligned["end"] * 1000)
                timings[idx]["start_ms"] = start_ms
                timings[idx]["end_ms"] = max(start_ms, end_ms)

            previous_end = 0
            for timing in timings:
                timing["start_ms"] = max(timing["start_ms"], previous_end)
                timing["end_ms"] = max(timing["end_ms"], timing["start_ms"])
                previous_end = timing["end_ms"]

            return timings

        logger.info("Whisper alignment unavailable; using heuristic timings")
        return timings

    def _build_word_timings_estimate(
        self,
        chunk_records: List[Dict],
        tokens: List[Dict],
    ) -> List[Dict]:
        timings: List[Dict] = []
        audio_offset = 0.0

        index = 0
        for record in chunk_records:
            chunk_tokens = []
            chunk_end = record["char_offset"] + len(record["text"])
            while index < len(tokens) and tokens[index]["char_start"] < chunk_end:
                chunk_tokens.append(tokens[index])
                index += 1

            if not chunk_tokens:
                audio_offset += record["duration"]
                continue

            total_weight = sum(token["weight"] for token in chunk_tokens)
            if total_weight == 0:
                audio_offset += record["duration"]
                continue

            leading_silence = max(0.0, record.get("leading_silence", 0.0))
            effective_duration = max(0.0, record["duration"] - leading_silence)
            remaining = effective_duration
            token_start = audio_offset + leading_silence

            for idx, token in enumerate(chunk_tokens):
                if idx == len(chunk_tokens) - 1:
                    token_duration = remaining
                else:
                    token_duration = (effective_duration * token["weight"]) / total_weight
                    remaining = max(0.0, remaining - token_duration)

                token_end = token_start + token_duration
                timings.append(
                    {
                        "token": token["value"],
                        "start_ms": int(round(token_start * 1000)),
                        "end_ms": int(round(token_end * 1000)),
                        "char_start": token["char_start"],
                        "char_end": token["char_end"],
                    }
                )
                token_start = token_end

            audio_offset += record["duration"]

        while index < len(tokens):
            token = tokens[index]
            current_ms = int(round(audio_offset * 1000))
            timings.append(
                {
                    "token": token["value"],
                    "start_ms": current_ms,
                    "end_ms": current_ms,
                    "char_start": token["char_start"],
                    "char_end": token["char_end"],
                }
            )
            index += 1

        return timings

    def _determine_token_weight(self, token: str) -> int:
        stripped = token.strip()
        if not stripped:
            return MIN_TOKEN_WEIGHT
        if stripped in PAUSE_TOKENS:
            return max(MIN_TOKEN_WEIGHT, len(stripped) + 8)
        if re.fullmatch(r"[^\w]+", stripped):
            return max(MIN_TOKEN_WEIGHT, len(stripped) + 4)
        return max(MIN_TOKEN_WEIGHT, len(stripped))

    def _tokenize(self, text: str, base_offset: int):
        for match in TOKEN_PATTERN.finditer(text):
            start = base_offset + match.start()
            end = base_offset + match.end()
            value = match.group()
            yield {
                "value": value,
                "char_start": start,
                "char_end": end,
                "length": end - start,
                "weight": self._determine_token_weight(value),
            }

    def _write_metadata(
        self,
        output_file: str,
        audio_tags: AudioTags,
        text: str,
        timings: List[Dict],
        duration_ms: int,
    ) -> None:
        metadata = {
            "book_title": audio_tags.book_title,
            "book_author": audio_tags.author,
            "chapter_index": audio_tags.idx,
            "chapter_title": audio_tags.title,
            "audio_file": os.path.basename(output_file),
            "duration_ms": duration_ms,
            "text": text,
            "words": timings,
        }

        metadata_path = f"{os.path.splitext(output_file)[0]}.json"

        with open(metadata_path, "w", encoding="utf-8") as fp:
            json.dump(metadata, fp, ensure_ascii=False)

        logger.info("Timing metadata written to %s", metadata_path)

    def estimate_cost(self, total_chars):
        return 0.0

    def __str__(self) -> str:
        return f"KokoroTTSProvider(device={self.device})"
