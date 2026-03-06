# AudioBook - Claude Code Guide

Personal project for generating high-quality audiobooks from EPUB files using Kokoro TTS, with synchronized word-level highlighting.

## Architecture Overview

Three main components:

1. **epubToAudioBook** (`apps/epubToAudioBook/`) - FastAPI backend that converts EPUBs to audiobooks using Kokoro TTS. Serves a web UI for uploading and managing books. Runs on port 8000.
2. **Audiobookshelf** (`apps/audiobookshelf/`) - Node.js media server (forked/vendored) for streaming generated audiobooks. Runs on port 3333.
3. **KokoroAndroid** (`apps/KokoroAndroid/`) - Native Android app (Kotlin + Jetpack Compose) with on-device ONNX TTS inference for local audiobook playback.

## Data Flow

```
EPUB upload → FastAPI (parse + chunk) → Kokoro TTS (synthesize) → WhisperX (word alignment)
  → FFmpeg (package .m4b) → data/generated/{book_id}/ → Audiobookshelf serves it
```

## Key Directories

| Path | Purpose |
|------|---------|
| `apps/epubToAudioBook/app/backend/main.py` | FastAPI server, all REST endpoints |
| `apps/epubToAudioBook/app/frontend/` | Web UI (vanilla JS) |
| `apps/epubToAudioBook/audiobook_generator/core/` | Core generation logic |
| `apps/epubToAudioBook/audiobook_generator/tts_providers/` | TTS backends (Kokoro, OpenAI, Azure, Edge, Piper) |
| `apps/epubToAudioBook/audiobook_generator/book_parsers/` | EPUB/PDF parsers |
| `apps/epubToAudioBook/audiobook_generator/utils/m4b_builder.py` | M4B packaging with FFmpeg |
| `apps/KokoroAndroid/app/src/main/java/com/example/kokoroandroid/` | Android app source |
| `scripts/` | Start/stop scripts and standalone conversion CLIs |
| `data/books/` | Uploaded EPUBs (gitignored) |
| `data/generated/` | Output audiobooks with manifests (gitignored) |
| `models/kokoro_model/` | Kokoro TTS weights (gitignored) |

## Tech Stack

- **TTS**: Kokoro 82M (PyTorch, local GPU/CPU)
- **Backend**: FastAPI + Uvicorn (Python 3.10+)
- **Audio**: FFmpeg, pydub, Mutagen
- **Alignment**: WhisperX / NeMo / torchaudio
- **Book parsing**: EbookLib, BeautifulSoup
- **Media server**: Audiobookshelf (Node.js 20+, Express, SQLite)
- **Android**: Kotlin, Jetpack Compose, ONNX Runtime
- **Containerization**: Docker support available

## Output Format

Each generated book lives in `data/generated/{book_id}/`:
- `manifest.json` - Book metadata, chapter list, asset paths
- `{title}.m4b` - Packaged audiobook (AAC, chapters, gapless)
- `{title}.epub` - Copy of source EPUB
- `0001_ChapterTitle.json` - Word-level timestamps for sync highlighting

## API Endpoints (FastAPI, port 8000)

- `POST /api/audiobooks` - Upload EPUB and start generation job
- `GET /api/audiobooks/{job_id}/status` - Poll generation progress
- `GET /api/books` - List all generated books
- `GET /api/books/{book_id}` - Get book manifest
- `GET /api/books/{book_id}/chapters/{idx}/audio` - Chapter WAV
- `GET /api/books/{book_id}/chapters/{idx}/metadata` - Chapter word timings
- `GET /api/books/{book_id}/assets/{name}` - Download m4b/epub

## Running Locally

```bash
# Start the generation service (port 8000)
./scripts/start_epub_service.sh

# Start Audiobookshelf (port 3333)
./scripts/start_audiobookshelf.sh

# Stop Audiobookshelf
./scripts/stop_audiobookshelf.sh
```

Key env vars: `KOKORO_DEVICE` (cuda:0/cpu), `HOST`, `PORT`, `ALIGNMENT_BACKEND` (whisperx/nemo/torchaudio).

## Deployment Status

Currently runs locally only. No cloud deployment configured. Services bind to `0.0.0.0` for LAN access.

## Roadmap

### Phase 1: Telegram Bot Integration (Next)
- Create a Telegram bot that accepts EPUB uploads on a channel/chat
- Bot triggers audiobook generation via the existing FastAPI backend
- Generated book is stored in `data/generated/` so it appears in Audiobookshelf automatically
- Goal: upload on phone via Telegram, book appears in app without touching the server

### Phase 2: Standalone App Store App (Future)
- Complete end-to-end independent mobile app for public release
- Users can generate and listen to audiobooks entirely within the app
- No server dependency - fully on-device processing (building on KokoroAndroid's ONNX approach)
- Publish to app stores

## Development Conventions

- Python code lives under `apps/epubToAudioBook/`, uses venv at `apps/epubToAudioBook/.venv/`
- Node code lives under `apps/audiobookshelf/`
- Android code lives under `apps/KokoroAndroid/`
- All user data goes in `data/` (gitignored except `.gitkeep` placeholders)
- Model weights go in `models/` (gitignored)
- Scripts in `scripts/` use env vars, never hardcode paths or secrets
- TTS providers follow `BaseTTSProvider` interface in `tts_providers/base_tts_provider.py`
- Book parsers follow `BaseBookParser` interface in `book_parsers/base_book_parser.py`
