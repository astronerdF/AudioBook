# AudioBook Workspace

This repository bundles everything needed to convert EPUB files into narrated audiobooks and stream them through Audiobookshelf. The layout keeps code tidy while ensuring personal content remains outside of Git.

## Directory Layout

```
apps/
  audiobookshelf/         # Audiobookshelf server (Node.js)
  epubToAudioBook/        # FastAPI + Kokoro generation service
scripts/                  # Helper launch scripts
models/                   # Optional TTS weights (e.g. Kokoro voices)
data/
  books/                  # User-supplied EPUB uploads (gitignored)
  generated/              # Generated audiobook packages (.m4b, JSON, metadata)
  logs/
    audiobookshelf/       # Audiobookshelf runtime logs
    generator/            # FastAPI generation logs
  audiobookshelf/         # Persistent Audiobookshelf config/metadata/backups
```

Everything under `data/` is ignored by Git (only `.gitkeep` placeholders are tracked) so uploads, logs, and configuration never leak to the public repo.

## Requirements

| Dependency | Version | Notes |
|------------|---------|-------|
| Python     | 3.10+   | Used by the EPUB generator service |
| Node.js    | 20+     | Required by Audiobookshelf |
| ffmpeg / ffprobe | latest | Needed for audio muxing |

Optional but recommended virtual environment setup:

```bash
cd apps/epubToAudioBook
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Audiobookshelf dependencies (`npm ci`) are installed automatically by the helper script on first launch.

## Getting Started

1. **Clone** the repository: `git clone <repo-url>`
2. **Add EPUBs** to `data/books/` (or upload from the web UI later).
3. **(Optional)** Drop any custom Kokoro voices into `models/`.

### Start the EPUB → Audio Service (port 8000)

```bash
./scripts/start_epub_service.sh
```

The script prepares `data/books`, `data/generated`, and `data/logs/generator`, activates `.venv` if present, exports the required environment variables, and runs uvicorn. Useful overrides:

| Variable | Purpose | Default |
|----------|---------|---------|
| `HOST` | Bind address | `0.0.0.0` |
| `PORT` | HTTP port | `8000` |
| `RELOAD` | FastAPI auto-reload (1/0) | `0` |
| `UVICORN_BIN` | Uvicorn executable | `uvicorn` |
| `ABS_DATA_DIR` | Workspace data root | `<repo>/data` |

Open `http://localhost:8000/` to upload EPUBs, choose voices, and monitor jobs. Output appears in `data/generated/<book-id>/` with the packaged `.m4b`, chapter audio/JSON, and a copy of the original EPUB.

### Start Audiobookshelf (port 3333)

```bash
./scripts/start_audiobookshelf.sh
```

This script bootstraps `data/audiobookshelf/{config,metadata,backups}` and `data/logs/audiobookshelf/`, installs/builds dependencies if needed, exports persistence paths, and launches Audiobookshelf:

```
npm start -- --host 0.0.0.0 --port 3333
```

Environment overrides:

| Variable | Purpose | Default |
|----------|---------|---------|
| `HOST` | Bind address | `0.0.0.0` |
| `PORT` | HTTP port | `3333` |
| `DATA_DIR` | Alternate data root | `<repo>/data` |

Logs are written to `data/logs/audiobookshelf/audiobookshelf-<timestamp>.log`; the PID file lives at `data/logs/audiobookshelf/audiobookshelf.pid`. Stop the service with:

```bash
kill $(cat data/logs/audiobookshelf/audiobookshelf.pid)
```

Complete the Audiobookshelf setup at `http://localhost:3333/audiobookshelf` and add `data/generated/` (or any other path) as your library.

### Connect Mobile Apps

Discover the host machine’s LAN IP (Linux example):

```bash
hostname -I | awk '{print $1}'
```

Use `http://<ip-address>:3333` as the server URL inside the Audiobookshelf Android/iOS app.

## Privacy & Git Hygiene

- `data/`, virtual environments, `.env` files, Node build artifacts, and caches are ignored by `.gitignore`.
- Helper scripts set environment variables rather than embedding secrets or IP addresses in code.
- Generated media and logs remain local unless you decide to publish them.

## Troubleshooting

- **Missing ffmpeg/ffprobe:** install via your package manager (e.g. `sudo apt install ffmpeg`).
- **GPU acceleration:** set `KOKORO_DEVICE=cuda:0` before launching the EPUB service.
- **Service errors:** inspect `data/logs/generator/` or `data/logs/audiobookshelf/` for timestamped logs.
- **Port already in use:** override `PORT` when invoking the scripts.

Enjoy building and listening!
