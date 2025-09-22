"""Utilities to package generated chapter audio into an .m4b container."""
from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable, Optional, Sequence

logger = logging.getLogger(__name__)

FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "ffmpeg")
FFPROBE_BIN = os.environ.get("FFPROBE_BIN", "ffprobe")


class M4BPackagingError(RuntimeError):
    """Raised when packaging into an m4b container fails."""


def _run_subprocess(args: Sequence[str], *, capture_output: bool = False) -> subprocess.CompletedProcess:
    """Run a subprocess and raise a helpful error on failure."""
    try:
        result = subprocess.run(
            args,
            check=True,
            text=True,
            capture_output=capture_output,
        )
        return result
    except FileNotFoundError as exc:  # pragma: no cover - depends on runtime env
        raise M4BPackagingError(f"Required binary not found: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        message = (
            f"Command '{' '.join(args)}' failed with exit code {exc.returncode}."
            f" Stdout: {stdout.strip()} Stderr: {stderr.strip()}"
        )
        raise M4BPackagingError(message) from exc


def _probe_duration_ms(audio_path: Path) -> int:
    """Return the duration of the audio file in milliseconds."""
    result = _run_subprocess(
        [
            FFPROBE_BIN,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nokey=1:noprint_wrappers=1",
            str(audio_path),
        ],
        capture_output=True,
    )
    try:
        duration_seconds = float((result.stdout or "0").strip())
    except ValueError as exc:  # pragma: no cover - unexpected probe output
        raise M4BPackagingError(f"Could not read duration for {audio_path}") from exc
    return int(round(duration_seconds * 1000))


def _slugify(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return cleaned or fallback


def _discover_cover_file(folder: Path) -> Optional[Path]:
    for candidate in ("cover.jpg", "Cover.jpg", "cover.jpeg", "cover.png", "Cover.png"):
        path = folder / candidate
        if path.exists() and path.is_file():
            return path
    return None


def _build_ffmetadata(
    *,
    title: str,
    author: str,
    chapters: Iterable[tuple[int, Path, str]],
) -> Path:
    """Create an ffmetadata file describing global tags and chapter markers."""
    fd, temp_path = tempfile.mkstemp(suffix=".ffmetadata")
    metadata_path = Path(temp_path)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(";FFMETADATA1\n")
        fh.write(f"title={title}\n")
        if author:
            fh.write(f"artist={author}\n")
        fh.write("encoder=ffmpeg\n")

        start_ms = 0
        for idx, path, label in chapters:
            duration_ms = _probe_duration_ms(path)
            end_ms = start_ms + duration_ms
            safe_label = label or f"Chapter {idx}"
            fh.write("\n[CHAPTER]\n")
            fh.write("TIMEBASE=1/1000\n")
            fh.write(f"START={start_ms}\n")
            fh.write(f"END={end_ms}\n")
            fh.write(f"title={safe_label}\n")
            start_ms = end_ms
    return metadata_path


def _build_file_list(chapters: Iterable[tuple[int, Path, str]]) -> Path:
    fd, temp_path = tempfile.mkstemp(suffix=".txt")
    file_list_path = Path(temp_path)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        for _, path, _ in chapters:
            fh.write(f"file '{path}'\n")
    return file_list_path


def _chapter_title_from_filename(path: Path, index: int) -> str:
    stem = path.stem
    stem = re.sub(r"^[0-9]+_?", "", stem)
    stem = stem.replace("_", " ").strip()
    return stem or f"Chapter {index}"


def package_m4b(
    output_folder: Path,
    *,
    book_id: str,
    book_title: str,
    book_author: str,
    audio_files: Iterable[tuple[int, str]],
) -> Optional[Path]:
    """Create an m4b audiobook from generated chapter audio files."""
    audio_entries = []
    for chapter_index, filename in audio_files:
        candidate = output_folder / filename
        if not candidate.exists():
            logger.warning("Skipping missing chapter audio: %s", candidate)
            continue
        audio_entries.append((chapter_index, candidate.resolve(), _chapter_title_from_filename(candidate, chapter_index)))

    if not audio_entries:
        logger.info("No chapter audio available for m4b packaging in %s", output_folder)
        return None

    audio_entries.sort(key=lambda item: item[0])

    title = book_title or book_id
    fallback_slug = _slugify(book_id, "book")
    output_name = f"{_slugify(title, fallback_slug)}.m4b"
    output_path = output_folder / output_name

    metadata_path = _build_ffmetadata(title=title, author=book_author, chapters=audio_entries)
    file_list_path = _build_file_list(audio_entries)
    cover_path = _discover_cover_file(output_folder)

    ffmpeg_args = [
        FFMPEG_BIN,
        "-hide_banner",
        "-loglevel",
        os.environ.get("FFMPEG_LOGLEVEL", "info"),
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(file_list_path),
        "-i",
        str(metadata_path),
    ]

    if cover_path is not None:
        ffmpeg_args.extend(["-i", str(cover_path)])

    ffmpeg_args.extend([
        "-map",
        "0:a:0",
    ])

    if cover_path is not None:
        ffmpeg_args.extend([
            "-map",
            "2:v:0",
        ])

    ffmpeg_args.extend([
        "-map_metadata",
        "1",
        "-map_chapters",
        "1",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
    ])

    if cover_path is not None:
        ffmpeg_args.extend([
            "-c:v",
            "mjpeg",
            "-disposition:v:0",
            "attached_pic",
        ])

    ffmpeg_args.extend([
        "-movflags",
        "+faststart",
        "-y",
        str(output_path),
    ])

    try:
        _run_subprocess(ffmpeg_args)
    finally:
        metadata_path.unlink(missing_ok=True)
        file_list_path.unlink(missing_ok=True)

    logger.info("Packaged m4b audiobook at %s", output_path)
    return output_path


__all__ = ["package_m4b", "M4BPackagingError"]
