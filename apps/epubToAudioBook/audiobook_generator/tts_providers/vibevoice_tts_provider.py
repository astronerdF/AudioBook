"""
VibeVoice TTS Provider for Dramatized Audiobooks

Uses Microsoft's VibeVoice model (community fork) for expressive,
multi-speaker voice synthesis with voice cloning support.

Features:
- Zero-shot voice cloning from 10-60s reference audio
- Up to 4 simultaneous speakers per generation
- Long-form context (up to 90 minutes continuous)
- Emotion control via [tone:STYLE] tags
- 1.5B and 7B model variants
"""

import json
import logging
import os
import re
import tempfile
import time
from typing import Dict, List, Optional

import numpy as np
import soundfile as sf

from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.core.text_analyzer import TextSegment, SegmentType
from audiobook_generator.core.voice_registry import VoiceProfile
from audiobook_generator.tts_providers.base_tts_provider import BaseTTSProvider
from audiobook_generator.utils.utils import set_audio_tags, pydub_merge_audio_segments

logger = logging.getLogger(__name__)

# VibeVoice supported tone tags for emotion control
VIBEVOICE_TONES = {
    "whisper", "soft", "excited", "angry", "sad", "amused",
    "serious", "pleading", "terrified", "pained", "strained",
    "annoyed", "cheerful", "calm", "dramatic",
}

# Default model configuration
DEFAULT_MODEL_ID = "microsoft/VibeVoice-1.5B"
DEFAULT_SAMPLE_RATE = 24000


class VibeVoiceTTSProvider(BaseTTSProvider):
    """TTS provider using Microsoft VibeVoice for dramatized audiobooks."""

    def __init__(self, config):
        super().__init__(config)
        self.device = self.config.device or "cpu"
        self.model = None
        self._model_id = getattr(
            self.config, "vibevoice_model", DEFAULT_MODEL_ID
        )

    def validate_config(self):
        if not getattr(self.config, "voice_name", None):
            self.config.voice_name = "narrator"
        if not getattr(self.config, "language", None):
            self.config.language = "en-US"

    def get_model(self):
        """Lazy-load the VibeVoice model."""
        if self.model is None:
            try:
                from vibevoice import VibeVoicePipeline
                logger.info(
                    "Loading VibeVoice model '%s' on device '%s'...",
                    self._model_id, self.device,
                )
                self.model = VibeVoicePipeline.from_pretrained(
                    self._model_id,
                    device=self.device,
                )
                logger.info("VibeVoice model loaded successfully.")
            except ImportError:
                raise ImportError(
                    "VibeVoice is not installed. Install with: "
                    "pip install vibevoice  (or pip install vibevoice[gpu])"
                )
        return self.model

    def get_break_string(self):
        return ""

    def get_output_file_extension(self):
        return "wav"

    def text_to_speech(self, text: str, output_file: str, audio_tags: AudioTags):
        """Standard single-voice TTS (backward compatible with base interface)."""
        self._synthesize_single_voice(text, output_file, audio_tags)

    def text_to_speech_multi_voice(
        self,
        segments: List[TextSegment],
        output_file: str,
        audio_tags: AudioTags,
        voice_profiles: Dict[str, VoiceProfile],
        narrator_profile: VoiceProfile,
    ):
        """Multi-voice TTS for dramatized audiobooks.

        Synthesizes each text segment with the appropriate character voice,
        using emotion tags where detected.

        Args:
            segments: List of TextSegments from the text analyzer.
            output_file: Output audio file path.
            audio_tags: Chapter metadata tags.
            voice_profiles: character_name -> VoiceProfile mapping.
            narrator_profile: Voice profile for narration segments.
        """
        temp_files = []
        segment_records = []

        with tempfile.TemporaryDirectory() as temp_dir:
            for i, segment in enumerate(segments):
                temp_file = os.path.join(temp_dir, f"seg_{i:05d}.wav")

                # Determine which voice to use
                if segment.type == SegmentType.NARRATION:
                    profile = narrator_profile
                elif segment.type == SegmentType.DIALOGUE and segment.character:
                    profile = voice_profiles.get(segment.character, narrator_profile)
                else:
                    profile = narrator_profile

                # Prepare text with emotion tags if applicable
                synth_text = self._prepare_text_with_emotion(
                    segment.text, segment.emotion
                )

                logger.info(
                    "Segment %d/%d: %s [%s] voice=%s emotion=%s len=%d",
                    i + 1, len(segments),
                    segment.type.value,
                    segment.character or "narrator",
                    profile.voice_id,
                    segment.emotion,
                    len(segment.text),
                )

                audio_stats = self._synthesize_segment(
                    synth_text, temp_file, profile
                )

                temp_files.append(temp_file)
                segment_records.append({
                    "segment_index": i,
                    "type": segment.type.value,
                    "character": segment.character,
                    "emotion": segment.emotion,
                    "voice_id": profile.voice_id,
                    "text": segment.text,
                    "audio_path": temp_file,
                    "duration": audio_stats["duration"],
                })

            # Merge all segment audio files into final output
            pydub_merge_audio_segments(
                temp_files, output_file, self.get_output_file_extension()
            )

        try:
            set_audio_tags(output_file, audio_tags)
        except ValueError as exc:
            logger.warning("Skipping metadata tags for %s: %s", output_file, exc)

        # Write dramatization metadata
        self._write_dramatization_metadata(
            output_file, audio_tags, segments, segment_records
        )

    def _prepare_text_with_emotion(
        self, text: str, emotion: Optional[str]
    ) -> str:
        """Wrap text with VibeVoice emotion tags if applicable."""
        if emotion and emotion in VIBEVOICE_TONES:
            return f"[tone:{emotion}] {text}"
        return text

    def _synthesize_segment(
        self,
        text: str,
        output_file: str,
        profile: VoiceProfile,
    ) -> Dict[str, float]:
        """Synthesize a single segment using the given voice profile."""
        last_exception = None

        for attempt in range(1, 4):
            try:
                model = self.get_model()

                # Build synthesis kwargs based on voice profile
                kwargs = {
                    "text": text,
                    "output_file": output_file,
                }

                if profile.reference_audio and os.path.exists(profile.reference_audio):
                    # Voice cloning mode
                    kwargs["reference_audio"] = profile.reference_audio
                    if profile.reference_text:
                        kwargs["reference_text"] = profile.reference_text
                elif profile.preset_voice:
                    # Preset voice mode
                    kwargs["voice"] = profile.preset_voice

                model.synthesize(**kwargs)
                return self._analyze_audio(output_file)

            except Exception as e:
                last_exception = e
                logger.warning(
                    "Synthesis attempt %d failed for segment: %s", attempt, e
                )
                if attempt < 3:
                    time.sleep(1)

        raise last_exception or Exception(
            "VibeVoice synthesis failed after all retry attempts"
        )

    def _synthesize_single_voice(
        self, text: str, output_file: str, audio_tags: AudioTags
    ):
        """Single-voice synthesis for backward compatibility."""
        max_chars = getattr(self.config, "vibevoice_chunk_chars", 5000)
        # VibeVoice handles longer context natively, so we can use larger chunks
        chunks = self._split_text_simple(text, max_chars)
        temp_files = []

        with tempfile.TemporaryDirectory() as temp_dir:
            for i, chunk in enumerate(chunks):
                temp_file = os.path.join(temp_dir, f"{i}.wav")
                profile = VoiceProfile(
                    voice_id="default",
                    display_name="Default",
                    preset_voice=self.config.voice_name,
                )
                self._synthesize_segment(chunk, temp_file, profile)
                temp_files.append(temp_file)

            pydub_merge_audio_segments(
                temp_files, output_file, self.get_output_file_extension()
            )

        try:
            set_audio_tags(output_file, audio_tags)
        except ValueError as exc:
            logger.warning("Skipping metadata tags for %s: %s", output_file, exc)

    def _analyze_audio(self, audio_path: str) -> Dict[str, float]:
        """Analyze audio file for duration and silence."""
        with sf.SoundFile(audio_path) as audio_file:
            sample_rate = audio_file.samplerate or 1
            frames = audio_file.frames

        if frames == 0:
            return {"duration": 0.0}

        return {"duration": frames / sample_rate}

    def _split_text_simple(self, text: str, max_chars: int) -> List[str]:
        """Split text into chunks at sentence boundaries."""
        if len(text) <= max_chars:
            return [text]

        chunks = []
        current = ""
        sentences = re.split(r'(?<=[.!?])\s+', text)

        for sentence in sentences:
            if len(current) + len(sentence) + 1 > max_chars and current:
                chunks.append(current.strip())
                current = sentence
            else:
                current = f"{current} {sentence}" if current else sentence

        if current.strip():
            chunks.append(current.strip())

        return chunks

    def _write_dramatization_metadata(
        self,
        output_file: str,
        audio_tags: AudioTags,
        segments: List[TextSegment],
        segment_records: List[dict],
    ) -> None:
        """Write dramatization metadata for the chapter."""
        metadata = {
            "book_title": audio_tags.book_title,
            "book_author": audio_tags.author,
            "chapter_index": audio_tags.idx,
            "chapter_title": audio_tags.title,
            "audio_file": os.path.basename(output_file),
            "total_duration_ms": int(
                sum(r["duration"] for r in segment_records) * 1000
            ),
            "segment_count": len(segments),
            "dialogue_count": sum(
                1 for s in segments if s.type == SegmentType.DIALOGUE
            ),
            "characters_in_chapter": list(set(
                s.character for s in segments
                if s.character
            )),
            "segments": [
                {
                    "index": r["segment_index"],
                    "type": r["type"],
                    "character": r["character"],
                    "emotion": r["emotion"],
                    "voice_id": r["voice_id"],
                    "text": r["text"],
                    "duration_ms": int(r["duration"] * 1000),
                }
                for r in segment_records
            ],
        }

        metadata_path = f"{os.path.splitext(output_file)[0]}_drama.json"
        with open(metadata_path, "w", encoding="utf-8") as fp:
            json.dump(metadata, fp, ensure_ascii=False, indent=2)

        logger.info("Dramatization metadata written to %s", metadata_path)

    def estimate_cost(self, total_chars):
        return 0.0  # Local model, no API cost

    def __str__(self) -> str:
        return f"VibeVoiceTTSProvider(model={self._model_id}, device={self.device})"
