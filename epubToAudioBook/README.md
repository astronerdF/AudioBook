# AudioBook Generator

Generate word-synchronised audiobooks from EPUB files using the Kokoro neural
TTS engine and a minimal FastAPI + vanilla JS web application.

## Highlights
- Upload EPUBs from the browser and get per-chapter WAV audio plus JSON
  metadata.
- Word-level timestamps created with a Whisper-based forced aligner power the
  karaoke-style highlighting in the reader.
- Automatic chapter splitting, manifest creation, and ID3 tagging suitable for
  Audiobookshelf or other managers.
- CPU-only operation works out of the box; CUDA GPUs are detected and used when
  available for faster synthesis and alignment.

## Requirements
- Python 3.10 or newer.
- `ffmpeg` in your `PATH` (needed by `pydub` for audio merging).
- (Optional) CUDA-capable GPU for faster generation.

### Python dependencies

Install everything with:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> The requirements include `kokoro`, `torch`, and `faster-whisper`. First
> installs may take a few minutes while wheels download.

## Running the Web App

The FastAPI backend serves both the API and static frontend:

```bash
uvicorn epubToAudioBook.app.backend.main:app --reload
```

Open `http://127.0.0.1:8000/` in your browser. The UI lets you:
1. Select a Kokoro voice.
2. Choose the chapter range (single chapter or entire book).
3. Upload an EPUB and start generation.
4. Play generated audio with live text highlighting.

Progress is tracked with background tasks. Once complete, the book appears in
the sidebar with downloadable chapters.

## Output Layout

Generated assets land under the repository root:

```
Books/              # Uploaded EPUBs (one per job)
logs/               # Per-job log files
out/<book-id>/      # Audio, JSON metadata, manifest.json
```

Each chapter produces:

- `<chapter>.wav` – merged Kokoro audio.
- `<chapter>.json` – metadata containing chapter text and `words` with
  `start_ms`/`end_ms` values.
- `manifest.json` – book-level summary consumed by the frontend.

## Configuration

Environment variables allow finer control:

| Variable | Purpose |
| --- | --- |
| `KOKORO_ALIGNMENT_MODEL` | Override the Whisper model used for forced alignment (default `medium.en`). |
| `KOKORO_ALIGNMENT_COMPUTE_TYPE` | Force `faster-whisper` compute precision (e.g. `float16`). |
| `KOKORO_DEVICE` | Hint for synthesis when auto-detection is undesirable. |

If no CUDA device is present the generator falls back to CPU automatically.

## Command-Line Interface

The project still ships the original CLI for scripted use:

```bash
python3 main.py <input.epub> out/<folder> --tts kokoro --output_text
```

Run `python3 main.py -h` to inspect every flag, including alternative TTS
providers.

## Docker Support

Sample Compose files live at the repository root:

- `docker-compose.kokoro-example.yml` – headless generation with Kokoro.
- `docker-compose.webui.yml` – spins up the FastAPI + frontend bundle.

Edit the environment variables inside the file(s) before running:

```bash
docker compose -f docker-compose.webui.yml up
```

## Development

- Static files for the web client: `app/frontend/`
- Backend service: `app/backend/main.py`
- Core generator logic: `audiobook_generator/`

Run tests with:

```bash
pytest
```

## License

Distributed under the MIT License. See `LICENSE` for details.
