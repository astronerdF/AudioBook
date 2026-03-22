#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = REPO_ROOT / "apps" / "epubToAudioBook"
DATA_ROOT = REPO_ROOT / "data"
DEFAULT_BOOKS_DIR = DATA_ROOT / "books"
DEFAULT_OUTPUT_DIR = DATA_ROOT / "generated"
DEFAULT_LOG_DIR = DATA_ROOT / "logs" / "generator"

if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
TTS_ROOT = APP_ROOT / "tts"
if str(TTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TTS_ROOT))

AVAILABLE_VOICES = [
    "af_heart",
    "af_bella",
    "am_fenrir",
    "bf_emma",
    "bm_fable",
]

DEFAULT_VOICE = AVAILABLE_VOICES[0]

os.environ.setdefault("ABS_WORKSPACE_ROOT", str(REPO_ROOT))
os.environ.setdefault("ABS_DATA_DIR", str(DATA_ROOT))
os.environ.setdefault("ABS_BOOKS_DIR", str(DEFAULT_BOOKS_DIR))
os.environ.setdefault("ABS_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR))
os.environ.setdefault("ABS_GENERATOR_LOG_DIR", str(DEFAULT_LOG_DIR))

from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.core.audiobook_generator import AudiobookGenerator
from audiobook_generator.utils.log_handler import generate_unique_log_path, setup_logging
from audiobook_generator.utils.m4b_builder import M4BPackagingError, package_m4b


def slugify(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")
    return sanitized.lower() or "book"


def ensure_unique_book_id(base_id: str, output_root: Path, overwrite: bool) -> str:
    if overwrite:
        return base_id

    candidate = base_id
    counter = 1
    while (output_root / candidate).exists():
        counter += 1
        candidate = f"{base_id}-{counter}"
    return candidate


def load_manifest(folder: Path) -> dict:
    manifest_path = folder / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found at {manifest_path}")
    with manifest_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def list_voices() -> None:
    for voice in AVAILABLE_VOICES:
        print(voice)


def build_config_namespace(
    *,
    input_file: Path,
    output_folder: Path,
    voice: str,
    device: str,
    workers: int,
    chunk_chars: int | None,
    log_level: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        input_file=str(input_file),
        output_folder=str(output_folder),
        tts="kokoro",
        voice_name=voice,
        language="en-US",
        device=device,
        log=log_level.upper(),
        preview=False,
        output_text=False,
        no_prompt=True,
        worker_count=max(1, workers),
        use_pydub_merge=True,
        verbose=False,
        emit_timestamps=False,
        kokoro_chunk_chars=chunk_chars,
        kokoro_devices=None,
        alignment_backend=None,
        alignment_device=device,
        alignment_model=None,
        alignment_batch_size=None,
        newline_mode="double",
        title_mode="auto",
        chapter_start=1,
        chapter_end=-1,
        remove_endnotes=False,
        remove_reference_numbers=False,
        search_and_replace_file="",
    )


def package_book(folder: Path, book_id: str, manifest: dict) -> Path | None:
    audio_metadata = [
        (chapter.get("index"), chapter.get("audio"))
        for chapter in manifest.get("chapters", [])
        if chapter.get("status") == "ready"
    ]
    audio_metadata = [
        (index, name) for index, name in audio_metadata if index is not None and name
    ]

    if not audio_metadata:
        logging.warning("Manifest for %s contains no ready chapters; skipping M4B packaging.", book_id)
        return None

    return package_m4b(
        folder,
        book_id=book_id,
        book_title=manifest.get("book_title") or book_id,
        book_author=manifest.get("book_author") or "",
        audio_files=audio_metadata,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert an EPUB file into an audiobook packaged as a single .m4b file."
    )
    parser.add_argument("--input", "-i", help="Path to the source EPUB file.")
    parser.add_argument(
        "--output-dir",
        "-o",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where generated output will be stored (default: %(default)s).",
    )
    parser.add_argument(
        "--voice",
        "-v",
        choices=AVAILABLE_VOICES,
        default=DEFAULT_VOICE,
        help="Kokoro voice to use (default: %(default)s).",
    )
    parser.add_argument(
        "--device",
        default="cuda",
        help="Device hint for Kokoro TTS (e.g. cuda, cuda:0, cpu). Default: %(default)s.",
    )
    # Alignment/word-matching is disabled for fastest conversion
    parser.add_argument(
        "--keep-wav",
        action="store_true",
        help="Do not delete per-chapter WAV files after successful .m4b packaging.",
    )
    parser.add_argument(
        "--book-id",
        help="Optional explicit book identifier. Defaults to a slugified filename.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Reuse the output folder if it already exists (files are not deleted).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel workers to use (default: %(default)s).",
    )
    parser.add_argument(
        "--chunk-chars",
        type=int,
        help="Override Kokoro chunk size (characters per synthesis request).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity for the generator (default: %(default)s).",
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="List available Kokoro voices and exit.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.list_voices:
        list_voices()
        if not args.input:
            return 0

    if not args.input:
        logging.error("No input EPUB provided. Use --input /path/to/book.epub.")
        return 1

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        logging.error("Input EPUB does not exist: %s", input_path)
        return 1
    if input_path.suffix.lower() != ".epub":
        logging.warning("Input file does not have .epub extension: %s", input_path)

    output_root = Path(args.output_dir).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    desired_id = slugify(args.book_id) if args.book_id else slugify(input_path.stem)
    book_id = ensure_unique_book_id(desired_id, output_root, args.overwrite)
    output_folder = output_root / book_id
    output_folder.mkdir(parents=True, exist_ok=True)

    log_file = generate_unique_log_path(book_id)
    setup_logging(args.log_level, log_file=log_file, is_worker=False)
    logging.info("Writing logs to %s", log_file)

    # Enforce GPU availability if CUDA is requested
    if args.device and str(args.device).startswith("cuda"):
        try:
            import torch  # type: ignore

            if not torch.cuda.is_available():
                logging.error("CUDA requested but torch reports no GPU. Aborting.")
                return 1
        except Exception as exc:  # pragma: no cover - environment specific
            logging.warning("Unable to verify CUDA availability via torch: %s", exc)
            # Let downstream raise if CUDA truly unavailable

    # Force no alignment/word matching for fastest path
    aligner = None

    config_args = build_config_namespace(
        input_file=input_path,
        output_folder=output_folder,
        voice=args.voice,
        device=args.device,
        # alignment disabled
        workers=args.workers,
        chunk_chars=args.chunk_chars,
        log_level=args.log_level,
    )

    config = GeneralConfig(config_args)
    config.log_file = log_file

    generator = AudiobookGenerator(config)
    logging.info("Starting conversion for %s (voice=%s, device=%s)", input_path, args.voice, args.device)

    generator.run()

    manifest = None
    try:
        manifest = load_manifest(output_folder)
    except FileNotFoundError as exc:
        logging.error("%s", exc)

    try:
        packaged = package_book(output_folder, book_id, manifest) if manifest else None
    except M4BPackagingError as exc:
        logging.error("Failed to package M4B for %s: %s", book_id, exc)
        packaged = None

    # Preserve original EPUB alongside outputs for convenience.
    try:
        epub_copy = output_folder / f"{book_id}.epub"
        shutil.copy2(input_path, epub_copy)
        logging.info("Copied source EPUB to %s", epub_copy)
        epub_copy_name = epub_copy.name
    except Exception as exc:
        logging.warning("Unable to copy source EPUB: %s", exc)
        epub_copy_name = None

    if manifest:
        assets = dict(manifest.get("assets") or {})
        if packaged:
            assets["m4b"] = Path(packaged).name
        if epub_copy_name:
            assets["epub"] = epub_copy_name
        if assets:
            manifest["assets"] = assets
            manifest_path = output_folder / "manifest.json"
            try:
                with manifest_path.open("w", encoding="utf-8") as handle:
                    json.dump(manifest, handle, ensure_ascii=False, indent=2)
                logging.debug("Updated manifest assets at %s", manifest_path)
            except Exception as exc:
                logging.warning("Failed to update manifest assets: %s", exc)

        # Optionally remove chapter WAV files to keep only the packaged .m4b
        if packaged and not args.keep_wav:
            removed = 0
            for chapter in manifest.get("chapters", []):
                audio_name = chapter.get("audio")
                if not audio_name:
                    continue
                wav_path = output_folder / audio_name
                try:
                    if wav_path.exists():
                        wav_path.unlink()
                        removed += 1
                        # Reflect removal in manifest for clarity
                        chapter["audio"] = None
                        # Optional status update to indicate packaging complete
                        if chapter.get("status") == "ready":
                            chapter["status"] = "packaged"
                except Exception as exc:
                    logging.debug("Could not remove %s: %s", wav_path, exc)

            # Persist manifest changes after cleanup
            try:
                with (output_folder / "manifest.json").open("w", encoding="utf-8") as handle:
                    json.dump(manifest, handle, ensure_ascii=False, indent=2)
                logging.info("Removed %d WAV chapter files after packaging.", removed)
            except Exception as exc:
                logging.warning("Failed to persist manifest after WAV cleanup: %s", exc)

    if packaged:
        logging.info("Audiobook packaged at %s", packaged)
        print(packaged)
        return 0

    logging.warning("Audiobook generation completed without an M4B package. Check logs for details.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
