"""FastAPI backend for the Kokoro audiobook application."""
from __future__ import annotations

import json
import logging
import re
import os
import shutil
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.routing import APIRouter
from fastapi.staticfiles import StaticFiles

from audiobook_generator.config.general_config import GeneralConfig
from audiobook_generator.core.audiobook_generator import AudiobookGenerator
from audiobook_generator.utils.log_handler import generate_unique_log_path

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(BASE_DIR / "tts"))
BOOKS_DIR = BASE_DIR / "Books"
OUTPUT_DIR = BASE_DIR / "out"
FRONTEND_DIR = BASE_DIR / "app" / "frontend"
LOGS_DIR = BASE_DIR / "logs"

DEFAULT_VOICE = "af_heart"
AVAILABLE_VOICES: List[str] = [
    "af_heart",
    "af_bella",
    "am_fenrir",
    "bf_emma",
    "bm_fable",
]

BOOKS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Kokoro Audiobook Server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix="/api")

tasks_status: Dict[str, Dict[str, str]] = {}
logger = logging.getLogger(__name__)


def _optional_int_from_env(key: str) -> Optional[int]:
    value = os.environ.get(key)
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        logger.warning("Ignoring invalid integer for %s: %s", key, value)
        return None


def _detect_kokoro_resources(device_hint: str) -> Dict[str, Optional[object]]:
    """Return adaptive configuration based on available GPU resources."""

    result = {
        "chunk_chars": 3000,
        "worker_count": 1,
        "primary_device": device_hint,
        "device_pool": None,
    }

    if not device_hint or not device_hint.startswith("cuda"):
        return result

    try:
        import torch

        if not torch.cuda.is_available():
            logger.warning("CUDA requested but torch reports no GPU. Falling back to CPU.")
            result["primary_device"] = "cpu"
            return result

        device_count = torch.cuda.device_count()
        if device_count == 0:
            logger.warning("No CUDA devices visible. Using CPU.")
            result["primary_device"] = "cpu"
            return result

        device_pool = []
        memory_gb = []
        for idx in range(device_count):
            props = torch.cuda.get_device_properties(idx)
            device_pool.append(f"cuda:{idx}")
            memory_gb.append(props.total_memory / (1024 ** 3))

        min_mem = min(memory_gb)
        scale = max(1.0, min(3.5, min_mem / 8.0))
        adaptive_chunk = int(3000 * scale)

        result["chunk_chars"] = adaptive_chunk
        result["worker_count"] = min(device_count, 4)
        result["primary_device"] = device_pool[0]
        result["device_pool"] = device_pool

        logger.info(
            "Detected %s CUDA device(s); chunk size=%s chars, workers=%s",
            device_count,
            adaptive_chunk,
            result["worker_count"],
        )
        return result
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Failed to detect CUDA resources: %s", exc)
        return result


def _slugify(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")
    return sanitized.lower() or "book"


def _ensure_unique_book_id(base_id: str) -> str:
    candidate = base_id
    counter = 1
    while (OUTPUT_DIR / candidate).exists():
        counter += 1
        candidate = f"{base_id}-{counter}"
    return candidate


def _load_manifest(book_id: str) -> Dict:
    manifest_path = OUTPUT_DIR / book_id / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Manifest not found")
    with manifest_path.open("r", encoding="utf-8") as manifest_file:
        return json.load(manifest_file)


def _safe_manifest_lookup(book_id: str, chapter_index: int) -> Dict[str, str]:
    manifest = _load_manifest(book_id)
    for chapter in manifest.get("chapters", []):
        if chapter.get("index") == chapter_index:
            return chapter
    raise HTTPException(status_code=404, detail="Chapter not found")


def _resolve_book_folder(book_id: str) -> Path:
    candidate = (OUTPUT_DIR / book_id).resolve()
    if OUTPUT_DIR not in candidate.parents and candidate != OUTPUT_DIR:
        raise HTTPException(status_code=400, detail="Invalid book identifier")
    return candidate


def _delete_book_artifacts(book_id: str) -> None:
    output_path = _resolve_book_folder(book_id)
    if output_path.exists():
        shutil.rmtree(output_path)

    epub_path = (BOOKS_DIR / f"{book_id}.epub").resolve()
    if epub_path.exists() and epub_path.is_file():
        epub_parent = epub_path.parent.resolve()
        if epub_parent == BOOKS_DIR.resolve():
            epub_path.unlink()

    for task_id, payload in list(tasks_status.items()):
        if payload.get("book_id") == book_id:
            tasks_status.pop(task_id, None)


def _run_generation(
    job_id: str,
    book_id: str,
    epub_path: Path,
    voice: str,
    device: str,
    chapter_start: int,
    chapter_end: int,
) -> None:
    tasks_status[job_id] = {"status": "processing", "book_id": book_id}

    output_folder = OUTPUT_DIR / book_id
    output_folder.mkdir(parents=True, exist_ok=True)

    resource_cfg = _detect_kokoro_resources(device)
    effective_device = resource_cfg["primary_device"]

    args = SimpleNamespace(
        input_file=str(epub_path),
        output_folder=str(output_folder),
        tts="kokoro",
        log="INFO",
        preview=False,
        output_text=True,
        no_prompt=True,
        worker_count=resource_cfg["worker_count"],
        use_pydub_merge=True,
        newline_mode="double",
        title_mode="auto",
        chapter_start=chapter_start,
        chapter_end=chapter_end,
        remove_endnotes=False,
        remove_reference_numbers=False,
        emit_timestamps=True,
        voice_name=voice,
        language="en-US",
        device=effective_device,
        kokoro_chunk_chars=resource_cfg["chunk_chars"],
        kokoro_devices=resource_cfg["device_pool"],
        kokoro_alignment_model=os.environ.get("KOKORO_ALIGNMENT_MODEL", "medium.en"),
        kokoro_alignment_compute_type=os.environ.get("KOKORO_ALIGNMENT_COMPUTE_TYPE"),
        kokoro_alignment_backend=os.environ.get("KOKORO_ALIGNMENT_BACKEND", "auto"),
        kokoro_alignment_batch_size=_optional_int_from_env("KOKORO_ALIGNMENT_BATCH_SIZE"),
    )

    config = GeneralConfig(args)
    config.log_file = generate_unique_log_path(book_id)

    try:
        AudiobookGenerator(config).run()
        tasks_status[job_id] = {"status": "completed", "book_id": book_id}
    except Exception as exc:  # pragma: no cover - defensive logging
        tasks_status[job_id] = {
            "status": "failed",
            "book_id": book_id,
            "detail": str(exc),
        }
        raise


@api_router.get("/voices/kokoro")
def list_voices() -> Dict[str, List[str]]:
    return {"voices": AVAILABLE_VOICES}


@api_router.get("/books")
def list_books() -> List[Dict]:
    books: List[Dict] = []
    for manifest_file in OUTPUT_DIR.glob("*/manifest.json"):
        with manifest_file.open("r", encoding="utf-8") as fp:
            try:
                manifest = json.load(fp)
            except json.JSONDecodeError:
                continue
        manifest["book_id"] = manifest.get("book_id") or manifest_file.parent.name
        books.append(manifest)
    return books


@api_router.get("/books/{book_id}")
def get_book(book_id: str) -> Dict:
    return _load_manifest(book_id)


@api_router.delete("/books/{book_id}")
def delete_book(book_id: str):
    folder = _resolve_book_folder(book_id)
    if not folder.exists():
        raise HTTPException(status_code=404, detail="Book not found")

    _delete_book_artifacts(book_id)
    return JSONResponse({"status": "deleted", "book_id": book_id})


@api_router.get("/books/{book_id}/chapters/{chapter_index}/metadata")
def get_chapter_metadata(book_id: str, chapter_index: int) -> Dict:
    chapter = _safe_manifest_lookup(book_id, chapter_index)
    metadata_path = OUTPUT_DIR / book_id / chapter["metadata"]
    if not metadata_path.exists():
        raise HTTPException(status_code=404, detail="Metadata file not found")
    with metadata_path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


@api_router.get("/books/{book_id}/chapters/{chapter_index}/audio")
def get_chapter_audio(book_id: str, chapter_index: int) -> FileResponse:
    chapter = _safe_manifest_lookup(book_id, chapter_index)
    audio_path = OUTPUT_DIR / book_id / chapter["audio"]
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(audio_path, media_type="audio/wav", filename=audio_path.name)


@api_router.get("/tasks/{task_id}")
def get_task_status(task_id: str) -> Dict[str, str]:
    status = tasks_status.get(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")
    return status


@api_router.post("/audiobooks", status_code=202)
async def create_audiobook(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    voice: str = Form(DEFAULT_VOICE),
    device: str = Form("cuda"),
    chapter_start: int = Form(1),
    chapter_end: int = Form(1),
) -> Dict[str, str]:
    if voice not in AVAILABLE_VOICES:
        raise HTTPException(status_code=400, detail="Unsupported voice selection")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    if chapter_start < 1:
        raise HTTPException(status_code=400, detail="chapter_start must be >= 1")
    if chapter_end not in (-1,) and chapter_end < chapter_start:
        raise HTTPException(status_code=400, detail="chapter_end must be >= chapter_start or -1")

    base_slug = _slugify(Path(file.filename).stem)
    book_id = _ensure_unique_book_id(base_slug)

    epub_path = BOOKS_DIR / f"{book_id}.epub"
    with epub_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    file.file.close()

    job_id = str(uuid.uuid4())
    tasks_status[job_id] = {"status": "queued", "book_id": book_id}
    background_tasks.add_task(
        _run_generation,
        job_id,
        book_id,
        epub_path,
        voice,
        device,
        chapter_start,
        chapter_end,
    )

    return {"job_id": job_id, "book_id": book_id}


app.include_router(api_router)
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


__all__ = ["app"]
