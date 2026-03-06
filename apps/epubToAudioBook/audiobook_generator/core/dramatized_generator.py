"""
Dramatized Audiobook Generator

Orchestrates the full pipeline for creating dramatized audiobooks:
1. Parse EPUB into chapters
2. Analyze each chapter for dialogue, characters, emotions
3. Build/load voice registry with character-to-voice mappings
4. Synthesize each segment with the appropriate voice
5. Package into final audiobook

This is the entry point for dramatized mode. It works alongside
(not replacing) the standard AudiobookGenerator for simple single-voice books.
"""

import json
import logging
import os
import time
from typing import List, Optional

from audiobook_generator.book_parsers.base_book_parser import get_book_parser
from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.core.text_analyzer import TextAnalyzer, TextSegment, SegmentType
from audiobook_generator.core.voice_registry import VoiceRegistry, VoiceProfile
from audiobook_generator.tts_providers.base_tts_provider import get_tts_provider

logger = logging.getLogger(__name__)


class DramatizedAudiobookGenerator:
    """Generates dramatized audiobooks with multi-voice, emotion-aware TTS."""

    def __init__(self, config: GeneralConfig):
        self.config = config
        self.voice_registry = None
        self.text_analyzer = None

    def run(self):
        """Main entry point for dramatized audiobook generation."""
        try:
            logger.info("Starting DRAMATIZED audiobook generation...")

            # Parse the book
            book_parser = get_book_parser(self.config)
            tts_provider = get_tts_provider(self.config)

            os.makedirs(self.config.output_folder, exist_ok=True)

            chapters = book_parser.get_chapters(tts_provider.get_break_string())
            chapters = [(title, text) for title, text in chapters if text.strip()]

            logger.info("Found %d chapters.", len(chapters))

            # Apply chapter range
            start = max(1, self.config.chapter_start or 1)
            end = self.config.chapter_end if self.config.chapter_end != -1 else len(chapters)
            chapters_to_process = chapters[start - 1:end]

            book_title = book_parser.get_book_title()
            book_author = book_parser.get_book_author()

            # Phase 1: Analyze all chapters to discover characters
            logger.info("=== Phase 1: Text Analysis ===")
            known_characters = self._load_character_list()
            self.text_analyzer = TextAnalyzer(known_characters)

            chapter_segments = []
            for title, text in chapters_to_process:
                logger.info("Analyzing chapter: %s", title)
                segments = self.text_analyzer.analyze_chapter(text)
                chapter_segments.append(segments)

            discovered_characters = self.text_analyzer.get_discovered_characters()
            character_stats = self.text_analyzer.get_character_stats()

            logger.info(
                "Discovered %d characters: %s",
                len(discovered_characters),
                ", ".join(
                    f"{name}({count})"
                    for name, count in character_stats.items()
                ),
            )

            # Phase 2: Build/load voice registry
            logger.info("=== Phase 2: Voice Registry ===")
            self.voice_registry = VoiceRegistry(
                self.config.output_folder,
                tts_backend=self.config.tts,
            )

            # Set up narrator voice
            if self.config.narrator_reference_audio:
                narrator = VoiceProfile(
                    voice_id="narrator",
                    display_name="Narrator",
                    reference_audio=self.config.narrator_reference_audio,
                )
                self.voice_registry.set_narrator_profile(narrator)

            # Auto-assign voices to characters that don't have mappings yet
            # For now, characters without explicit voice assignments get narrator voice
            # TODO: In future sessions, add voice cloning setup UI and character voice config
            unassigned = [
                c for c in discovered_characters
                if not self.voice_registry.get_voice_for_character(c)
            ]
            if unassigned:
                logger.info(
                    "%d characters need voice assignments: %s",
                    len(unassigned),
                    ", ".join(unassigned),
                )
                # For now, mark them but use narrator voice
                # Real voice assignment will be implemented with voice cloning UI
                for character in unassigned:
                    placeholder = VoiceProfile(
                        voice_id=f"char_{character.lower().replace(' ', '_')}",
                        display_name=character,
                        description=f"Voice for {character} (needs assignment)",
                    )
                    self.voice_registry.assign_voice(character, placeholder)

            self.voice_registry.save()

            # Write analysis report
            self._write_analysis_report(
                book_title, book_author,
                chapters_to_process, chapter_segments,
                character_stats,
            )

            # Phase 3: Synthesize chapters with multi-voice
            logger.info("=== Phase 3: Multi-Voice Synthesis ===")

            # Check if TTS provider supports multi-voice
            has_multi_voice = hasattr(tts_provider, 'text_to_speech_multi_voice')

            results = []
            for chapter_idx, ((title, text), segments) in enumerate(
                zip(chapters_to_process, chapter_segments),
                start=start,
            ):
                logger.info(
                    "Synthesizing chapter %d: %s (%d segments)",
                    chapter_idx, title, len(segments),
                )

                output_file = os.path.join(
                    self.config.output_folder,
                    f"{chapter_idx:04d}_{title}.{tts_provider.get_output_file_extension()}",
                )

                audio_tags = AudioTags(title, book_author, book_title, chapter_idx)

                try:
                    if has_multi_voice:
                        # Build voice profile map for this chapter's characters
                        voice_profiles = {}
                        for seg in segments:
                            if seg.character:
                                profile = self.voice_registry.get_voice_for_character(
                                    seg.character
                                )
                                if profile:
                                    voice_profiles[seg.character] = profile

                        tts_provider.text_to_speech_multi_voice(
                            segments=segments,
                            output_file=output_file,
                            audio_tags=audio_tags,
                            voice_profiles=voice_profiles,
                            narrator_profile=self.voice_registry.get_narrator_profile(),
                        )
                    else:
                        # Fallback: use standard single-voice TTS
                        logger.warning(
                            "TTS provider '%s' doesn't support multi-voice. "
                            "Using single-voice mode.",
                            self.config.tts,
                        )
                        tts_provider.text_to_speech(text, output_file, audio_tags)

                    results.append((chapter_idx, True))
                    logger.info("Chapter %d synthesized successfully.", chapter_idx)

                except Exception as e:
                    logger.exception(
                        "Failed to synthesize chapter %d: %s", chapter_idx, e
                    )
                    results.append((chapter_idx, False))

            # Write manifest
            self._write_manifest(
                book_title, book_author,
                tts_provider.get_output_file_extension(),
                chapters_to_process, results, start,
            )

            failed = [idx for idx, success in results if not success]
            if failed:
                logger.warning(
                    "Dramatized generation completed with %d failed chapters: %s",
                    len(failed), failed,
                )
            else:
                logger.info(
                    "Dramatized generation completed successfully for all %d chapters.",
                    len(results),
                )

        except Exception as e:
            logger.exception("Error during dramatized audiobook generation: %s", e)

    def _load_character_list(self) -> Optional[List[str]]:
        """Load a pre-defined character list if provided."""
        path = self.config.character_list
        if not path or not os.path.exists(path):
            return None

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "characters" in data:
            return data["characters"]

        return None

    def _write_analysis_report(
        self,
        book_title: str,
        book_author: str,
        chapters: list,
        chapter_segments: list,
        character_stats: dict,
    ):
        """Write a detailed analysis report for review before synthesis."""
        report = {
            "book_title": book_title,
            "book_author": book_author,
            "analysis_timestamp": int(time.time() * 1000),
            "total_chapters": len(chapters),
            "characters": {
                name: {
                    "dialogue_count": count,
                    "voice_id": (
                        self.voice_registry.get_voice_for_character(name).voice_id
                        if self.voice_registry.get_voice_for_character(name)
                        else None
                    ),
                }
                for name, count in character_stats.items()
            },
            "chapters": [],
        }

        for i, ((title, _text), segments) in enumerate(
            zip(chapters, chapter_segments)
        ):
            chapter_chars = set()
            dialogue_count = 0
            narration_count = 0
            emotions_found = set()

            for seg in segments:
                if seg.type == SegmentType.DIALOGUE:
                    dialogue_count += 1
                    if seg.character:
                        chapter_chars.add(seg.character)
                    if seg.emotion:
                        emotions_found.add(seg.emotion)
                else:
                    narration_count += 1

            report["chapters"].append({
                "index": i,
                "title": title,
                "total_segments": len(segments),
                "dialogue_segments": dialogue_count,
                "narration_segments": narration_count,
                "characters": sorted(chapter_chars),
                "emotions": sorted(emotions_found),
            })

        report_path = os.path.join(self.config.output_folder, "analysis_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info("Analysis report written to %s", report_path)

    def _write_manifest(
        self,
        book_title: str,
        book_author: str,
        audio_extension: str,
        chapters: list,
        results: list,
        start_idx: int,
    ):
        """Write the book manifest (compatible with existing format)."""
        success_map = {idx: success for idx, success in results}
        chapters_manifest = []

        for offset, (title, _) in enumerate(chapters, start=start_idx):
            base_name = f"{offset:04d}_{title}"
            chapters_manifest.append({
                "index": offset,
                "title": title,
                "audio": f"{base_name}.{audio_extension}",
                "metadata": f"{base_name}_drama.json",
                "status": "ready" if success_map.get(offset, False) else "failed",
            })

        payload = {
            "book_id": os.path.basename(os.path.normpath(self.config.output_folder)),
            "book_title": book_title,
            "book_author": book_author,
            "dramatized": True,
            "generated_ms": int(time.time() * 1000),
            "voice_registry": self.voice_registry.REGISTRY_FILENAME,
            "chapters": chapters_manifest,
        }

        manifest_path = os.path.join(self.config.output_folder, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        logger.info("Manifest written to %s", manifest_path)
