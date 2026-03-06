"""
Scan data/generated/ for every book directory that has a manifest.
For each with failed chapters, find the matching EPUB in data/books/
and regenerate.
"""
import json
import logging
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "tts"))

from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.core.audiobook_generator import AudiobookGenerator
from audiobook_generator.utils.log_handler import setup_logging

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]        # AudioBook/
DATA_ROOT    = Path(os.environ.get("ABS_DATA_DIR",         PROJECT_ROOT / "data"))
BOOKS_DIR    = Path(os.environ.get("ABS_BOOKS_DIR",        DATA_ROOT / "books"))
OUTPUT_DIR   = Path(os.environ.get("ABS_OUTPUT_DIR",       DATA_ROOT / "generated"))
LOGS_DIR     = Path(os.environ.get("ABS_GENERATOR_LOG_DIR",DATA_ROOT / "logs" / "generator"))

DEFAULT_VOICE   = "af_heart"
DEFAULT_ALIGNER = "whisperx"


def find_epub_for_book(book_id: str) -> Path | None:
    """Find the EPUB in data/books/ whose stem matches book_id (case-insensitive)."""
    book_id_lower = book_id.lower().replace("-", "").replace("_", "").replace(" ", "")
    for epub in BOOKS_DIR.rglob("*.epub"):
        stem = epub.stem.lower().replace("-", "").replace("_", "").replace(" ", "")
        if stem == book_id_lower or book_id_lower.startswith(stem) or stem.startswith(book_id_lower):
            return epub
    return None


def check_and_fix():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    setup_logging("INFO", str(LOGS_DIR / "check_and_regenerate.log"))
    logger = logging.getLogger(__name__)

    # ── scan all manifest files under data/generated/ ────────────────────────
    manifests = list(OUTPUT_DIR.rglob("manifest.json"))
    logger.info(f"Found {len(manifests)} manifest(s) in {OUTPUT_DIR}")

    to_generate = []  # list of (book_id, epub_path, book_output_folder)

    for mpath in manifests:
        book_output_folder = mpath.parent
        try:
            manifest  = json.loads(mpath.read_text(encoding="utf-8"))
            book_id   = manifest.get("book_id") or book_output_folder.name
            chapters  = manifest.get("chapters", [])
            failed    = [c for c in chapters if c.get("status") != "ready"]
        except Exception as e:
            logger.error(f"Cannot read {mpath}: {e}")
            continue

        if not failed:
            logger.info(f"  ✅ {book_id}  ({len(chapters)} chapters ready)")
            continue

        epub = find_epub_for_book(book_id)
        if epub is None:
            # fallback: try the folder name
            epub = find_epub_for_book(book_output_folder.name)

        if epub is None:
            logger.warning(f"  ⚠️  {book_id} — {len(failed)}/{len(chapters)} failed but no EPUB found")
            continue

        logger.info(f"  ❌ {book_id} — {len(failed)}/{len(chapters)} failed  [epub: {epub.name}]")
        to_generate.append((book_id, epub, book_output_folder))

    if not to_generate:
        logger.info("All books are properly generated. Nothing to do.")
        return

    logger.info(f"\n▶  Regenerating {len(to_generate)} book(s)...\n")

    for book_id, epub, book_output_folder in to_generate:
        logger.info(f"Generating  {book_id}  →  {book_output_folder}")
        book_output_folder.mkdir(parents=True, exist_ok=True)

        args = SimpleNamespace(
            input_file   = str(epub),
            output_folder= str(book_output_folder),
            tts          = "kokoro",
            log          = "INFO",
            preview      = False,
            output_text  = True,
            no_prompt    = True,
            worker_count = 4,
            use_pydub_merge    = True,
            newline_mode       = "double",
            title_mode         = "auto",
            chapter_start      = 1,
            chapter_end        = -1,
            remove_endnotes    = False,
            remove_reference_numbers = False,
            emit_timestamps    = True,
            voice_name         = DEFAULT_VOICE,
            language           = "en-US",
            device             = "cuda",
            kokoro_chunk_chars = 3000,
            kokoro_devices     = ["cuda:0"],
            alignment_backend  = DEFAULT_ALIGNER,
            alignment_device   = "cuda",
            alignment_model    = None,
            alignment_batch_size = None,
            verbose            = False,
            search_and_replace_file = "",
        )

        config          = GeneralConfig(args)
        config.log_file = str(LOGS_DIR / f"{book_id}.log")

        try:
            AudiobookGenerator(config).run()
            logger.info(f"✅  Done: {book_id}")
        except Exception as e:
            logger.error(f"❌  Failed {book_id}: {e}")

    logger.info("All done.")

if __name__ == "__main__":
    check_and_fix()
