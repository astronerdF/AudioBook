# AudioBook - Claude Code Guide

Personal project for generating high-quality audiobooks from EPUB files using Kokoro TTS and VibeVoice TTS, with synchronized word-level highlighting and dramatized multi-voice support.

## Architecture Overview

Four main components:

1. **epubToAudioBook** (`apps/epubToAudioBook/`) - FastAPI backend that converts EPUBs to audiobooks using Kokoro TTS. Serves a web UI for uploading and managing books. Runs on port 8000.
2. **Audiobookshelf** (`apps/audiobookshelf/`) - Node.js media server (forked/vendored) for streaming generated audiobooks. Runs on port 3333.
3. **KokoroAndroid** (`apps/KokoroAndroid/`) - Native Android app (Kotlin + Jetpack Compose) with on-device ONNX TTS inference for local audiobook playback.
4. **Chrome Reader** (`apps/chrome-reader/`) - Chrome extension that reads any webpage aloud using Kokoro TTS with word-level highlighting. Lightweight FastAPI TTS server on port 8008.

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
| `apps/epubToAudioBook/audiobook_generator/tts_providers/` | TTS backends (Kokoro, VibeVoice, OpenAI, Azure, Edge, Piper) |
| `apps/epubToAudioBook/audiobook_generator/book_parsers/` | EPUB/PDF parsers |
| `apps/epubToAudioBook/audiobook_generator/utils/m4b_builder.py` | M4B packaging with FFmpeg |
| `apps/KokoroAndroid/app/src/main/java/com/example/kokoroandroid/` | Android app source |
| `scripts/` | Start/stop scripts and standalone conversion CLIs |
| `data/books/` | Uploaded EPUBs (gitignored) |
| `data/generated/` | Output audiobooks with manifests (gitignored) |
| `models/kokoro_model/` | Kokoro TTS weights (gitignored) |
| `apps/chrome-reader/server/tts_server.py` | Lightweight TTS server for Chrome Reader (port 8008) |
| `apps/chrome-reader/extension/` | Chrome extension (MV3) - content scripts, popup, background |

## Tech Stack

- **TTS**: Kokoro 82M (PyTorch, local GPU/CPU), VibeVoice 1.5B/7B (multi-voice, voice cloning)
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

### Chrome Reader

```bash
# Start TTS server (port 8008)
./apps/chrome-reader/server/start_server.sh

# Load extension: chrome://extensions/ → Developer mode → Load unpacked → select apps/chrome-reader/extension/
```

Key env vars: `KOKORO_DEVICE` (cuda:0/cpu), `PORT` (default 8008).

## Deployment Status

Currently runs locally only. No cloud deployment configured. Services bind to `0.0.0.0` for LAN access.

## Roadmap

### Phase 0: Dramatized Audiobook System (ACTIVE - In Progress)

**Goal**: Build a dramatized audiobook system (like Red Rising audiobooks) with multi-voice, emotion-aware TTS using Microsoft VibeVoice. Ultimate target: dramatized Game of Thrones audiobooks.

**Architecture**:
```
EPUB → TextAnalyzer (dialogue/character/emotion detection)
     → VoiceRegistry (character-to-voice mapping, voice cloning refs)
     → VibeVoice TTS (multi-voice synthesis with [tone:STYLE] tags)
     → DramatizedGenerator (orchestration)
     → M4B packaging
```

**New files created**:
| File | Purpose | Status |
|------|---------|--------|
| `audiobook_generator/core/text_analyzer.py` | Parses chapters into narration/dialogue segments with character attribution and emotion detection | DONE |
| `audiobook_generator/core/voice_registry.py` | Manages character→voice mappings, persisted per book as JSON | DONE |
| `audiobook_generator/core/dramatized_generator.py` | Orchestrates full dramatized pipeline (analyze→assign→synthesize) | DONE |
| `audiobook_generator/tts_providers/vibevoice_tts_provider.py` | VibeVoice TTS provider with multi-voice + voice cloning support | DONE (skeleton) |

**VibeVoice TTS facts**:
- Open-source model from Microsoft Research (community fork: `vibevoice-community/VibeVoice`)
- 1.5B model: MOS 4.3, ~8 GB VRAM, RTF ~0.2 | 7B model: highest quality, ~24 GB VRAM
- Zero-shot voice cloning from 10-60s reference audio
- Up to 4 speakers per generation, 90 min continuous synthesis
- Emotion via `[tone:STYLE]` tags (whisper, excited, angry, sad, etc.)
- Install: `pip install vibevoice` or `pip install vibevoice[gpu]`
- Model weights: `microsoft/VibeVoice-1.5B` on HuggingFace

**What's done (Session 1)**:
- [x] Text analysis pipeline (dialogue detection, character extraction, emotion hints from speech verbs)
- [x] Character voice registry (persistent per-book JSON, voice cloning profile support)
- [x] VibeVoice TTS provider (multi-voice API, emotion tags, voice cloning mode)
- [x] Dramatized generator orchestrator (3-phase: analyze → assign voices → synthesize)
- [x] Config extensions for dramatized mode

**What's next (Session 2)**:
- [ ] Install VibeVoice and test basic synthesis on GPU
- [ ] Test text analyzer on a Game of Thrones chapter (validate dialogue/character detection)
- [ ] Collect/record reference audio samples for key GoT characters
- [ ] Build voice cloning pipeline (reference audio → VoiceProfile)
- [ ] Wire dramatized mode into FastAPI endpoints
- [ ] Test end-to-end single chapter generation

**What's next (Session 3+)**:
- [ ] Improve character detection with NER (spaCy) for better accuracy
- [ ] Add scene-level context awareness (e.g., battle vs. quiet conversation)
- [ ] Implement sound effects layer (ambient sounds, transitions)
- [ ] Build character voice configuration UI in web frontend
- [ ] Full Game of Thrones book generation and quality evaluation
- [ ] Optimize for batch generation (multiple chapters, GPU scheduling)

### Phase 1: Telegram Bot Integration
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


## Version Control Requirements

**CRITICAL: Git version control must be maintained religiously.**

- Commit all changes to the repository frequently
- Use descriptive commit messages that explain what changed and why
- Never leave significant changes uncommitted
- Before making major modifications, ensure the current state is committed
- This is essential for tracking experiments, rollback capability, and collaboration
- **NEVER add "Co-Authored-By" lines to commit messages**
