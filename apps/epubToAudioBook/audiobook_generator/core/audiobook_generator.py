import json
import logging
import multiprocessing
import os
import time
from tqdm import tqdm

from audiobook_generator.book_parsers.base_book_parser import get_book_parser
from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.core.audio_tags import AudioTags
from audiobook_generator.tts_providers.base_tts_provider import get_tts_provider
from audiobook_generator.utils.log_handler import setup_logging

logger = logging.getLogger(__name__)

# Global variable to hold the TTS provider instance in each worker process
tts_provider = None

def init_worker(config, log_level, log_file, is_worker):
    """Initializer for the worker process."""
    global tts_provider
    setup_logging(log_level, log_file, is_worker)
    if getattr(config, "kokoro_devices", None):
        identity = multiprocessing.current_process()._identity
        worker_idx = identity[0] - 1 if identity else 0
        devices = config.kokoro_devices
        if devices:
            assigned = devices[worker_idx % len(devices)]
            config.device = assigned
    tts_provider = get_tts_provider(config)


def confirm_conversion():
    logger.info("Do you want to continue? (y/n)")
    answer = input()
    if answer.lower() != "y":
        logger.info("Aborted.")
        exit(0)


def get_total_chars(chapters):
    total_characters = 0
    for title, text in chapters:
        total_characters += len(text)
    return total_characters


class AudiobookGenerator:
    def __init__(self, config: GeneralConfig):
        self.config = config

    def __str__(self) -> str:
        return f"{self.config}"

    def process_chapter(self, idx, title, text, book_title, book_author):
        """Process a single chapter: write text (if needed) and convert to audio."""
        try:
            logger.info(f"Processing chapter {idx}: {title}")
            logger.debug(f"Chapter {idx} character count: {len(text)}")

            global tts_provider

            # Save chapter text if required
            if self.config.output_text:
                text_file = os.path.join(self.config.output_folder, f"{idx:04d}_{title}.txt")
                logger.debug(f"Writing chapter text to {text_file}")
                with open(text_file, "w", encoding="utf-8") as f:
                    f.write(text)

            # Skip audio generation in preview mode
            if self.config.preview:
                return True

            # Generate audio file
            output_file = os.path.join(
                self.config.output_folder,
                f"{idx:04d}_{title}.{tts_provider.get_output_file_extension()}",
            )
            logger.debug(f"Output audio file: {output_file}")

            audio_tags = AudioTags(
                title, book_author, book_title, idx
            )
            
            logger.debug(f"Starting TTS for chapter {idx}")
            tts_provider.text_to_speech(text, output_file, audio_tags)

            logger.info(f"✅ Converted chapter {idx}: {title}, output file: {output_file}")

            return True
        except Exception as e:
            logger.exception(f"Error processing chapter {idx}, error: {e}")
            return False

    def process_chapter_wrapper(self, args):
        """Wrapper for process_chapter to handle unpacking args for imap."""
        idx, title, text, book_title, book_author = args
        return idx, self.process_chapter(idx, title, text, book_title, book_author)

    def run(self):
        if self.config.verbose:
            logger.setLevel(logging.DEBUG)

        try:
            logger.info("Starting audiobook generation...")
            book_parser = get_book_parser(self.config)
            main_tts_provider = get_tts_provider(self.config)

            os.makedirs(self.config.output_folder, exist_ok=True)
            chapters = book_parser.get_chapters(main_tts_provider.get_break_string())
            # Filter out empty or very short chapters
            chapters = [(title, text) for title, text in chapters if text.strip()]

            logger.info(f"Chapters count: {len(chapters)}.")

            # Check chapter start and end args
            if self.config.chapter_start < 1 or self.config.chapter_start > len(chapters):
                raise ValueError(
                    f"Chapter start index {self.config.chapter_start} is out of range. Check your input."
                )
            if self.config.chapter_end < -1 or self.config.chapter_end > len(chapters):
                raise ValueError(
                    f"Chapter end index {self.config.chapter_end} is out of range. Check your input."
                )
            if self.config.chapter_end == -1:
                self.config.chapter_end = len(chapters)
            if self.config.chapter_start > self.config.chapter_end:
                raise ValueError(
                    f"Chapter start index {self.config.chapter_start} is larger than chapter end index {self.config.chapter_end}. Check your input."
                )

            logger.info(
                f"Converting chapters from {self.config.chapter_start} to {self.config.chapter_end}."
            )

            # Initialize total_characters to 0
            total_characters = get_total_chars(
                chapters[self.config.chapter_start - 1 : self.config.chapter_end]
            )
            logger.info(f"Total characters in selected book chapters: {total_characters}")
            rough_price = main_tts_provider.estimate_cost(total_characters)
            logger.info(f"Estimate book voiceover would cost you roughly: ${rough_price:.2f}\n")

            # Prompt user to continue if not in preview mode
            if self.config.no_prompt:
                logger.info("Skipping prompt as passed parameter no_prompt")
            elif self.config.preview:
                logger.info("Skipping prompt as in preview mode")
            else:
                confirm_conversion()

            # Prepare chapters for processing
            chapters_to_process = chapters[self.config.chapter_start - 1 : self.config.chapter_end]
            book_title = book_parser.get_book_title()
            book_author = book_parser.get_book_author()
            tasks = [
                (idx, title, text, book_title, book_author)
                for idx, (title, text) in enumerate(
                    chapters_to_process, start=self.config.chapter_start
                )
            ]

            # Track failed chapters
            failed_chapters = []

            # Use multiprocessing to process chapters in parallel
            mp_context = multiprocessing
            if (
                getattr(self.config, "tts", None) == "kokoro"
                and isinstance(getattr(self.config, "device", None), str)
                and self.config.device.startswith("cuda")
            ):
                try:
                    mp_context = multiprocessing.get_context("spawn")
                    logger.debug(
                        "Using 'spawn' multiprocessing context for CUDA-enabled Kokoro jobs."
                    )
                except ValueError:
                    logger.warning(
                        "Failed to switch multiprocessing context to 'spawn'; continuing with default."
                    )

            with mp_context.Pool(
                processes=self.config.worker_count,
                initializer=init_worker,
                initargs=(self.config, self.config.log, self.config.log_file, True),
            ) as pool:
                # Process chapters and collect results
                results = []
                for idx, success in tqdm(
                    pool.imap_unordered(self.process_chapter_wrapper, tasks),
                    total=len(tasks),
                    desc="Converting chapters"
                ):
                    results.append((idx, success))
                # Check for failed chapters
                for idx, success in results:
                    if not success:
                        chapter_title = chapters_to_process[idx - self.config.chapter_start][0]
                        failed_chapters.append((idx, chapter_title))

            if failed_chapters:
                logger.warning("The following chapters failed to convert:")
                for idx, title in failed_chapters:
                    logger.warning(f"  - Chapter {idx}: {title}")
                logger.info(f"Conversion completed with {len(failed_chapters)} failed chapters. Check your output directory: {self.config.output_folder} and log file: {self.config.log_file} for more details.")
            else:
                logger.info(f"All chapters converted successfully. Check your output directory: {self.config.output_folder}")

            self._write_manifest(
                book_title,
                book_author,
                main_tts_provider.get_output_file_extension(),
                chapters_to_process,
                results,
            )

        except KeyboardInterrupt:
            logger.info("Audiobook generation process interrupted by user (Ctrl+C).")
        except Exception as e:
            logger.exception(f"Error during audiobook generation: {e}")
        finally:
            logger.debug("AudiobookGenerator.run() method finished.")

    def _write_manifest(
        self,
        book_title: str,
        book_author: str,
        audio_extension: str,
        chapters_to_process,
        results,
    ) -> None:
        try:
            os.makedirs(self.config.output_folder, exist_ok=True)
            manifest_path = os.path.join(self.config.output_folder, "manifest.json")

            success_map = {idx: success for idx, success in results}
            chapters_manifest = []

            for offset, (title, _) in enumerate(chapters_to_process, start=self.config.chapter_start):
                base_name = f"{offset:04d}_{title}"
                chapters_manifest.append(
                    {
                        "index": offset,
                        "title": title,
                        "audio": f"{base_name}.{audio_extension}",
                        "metadata": f"{base_name}.json",
                        "status": "ready" if success_map.get(offset, False) else "failed",
                    }
                )

            payload = {
                "book_id": os.path.basename(os.path.normpath(self.config.output_folder)),
                "book_title": book_title,
                "book_author": book_author,
                "generated_ms": int(time.time() * 1000),
                "chapters": chapters_manifest,
            }

            with open(manifest_path, "w", encoding="utf-8") as manifest_file:
                json.dump(payload, manifest_file, ensure_ascii=False, indent=2)

            logger.info("Book manifest written to %s", manifest_path)
        except Exception:
            logger.exception("Failed to write book manifest")
