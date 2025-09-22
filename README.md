# AudioBook Workspace

This repository contains two main pieces:

- `epubToAudioBook/`: FastAPI + Kokoro pipeline that turns EPUB uploads into narrated audio.
- `audiobookshelf/`: The Audiobookshelf server for browsing and streaming finished audiobooks.

## Quick Start

### 1. Generate audiobooks from EPUB

Use the helper script to bring up the web UI on port 8000:

```bash
./start_epub_service.sh
```

The script automatically activates `.venv` if present, then runs `uvicorn epubToAudioBook.app.backend.main:app --host 0.0.0.0 --port 8000`. Visit `http://localhost:8000/` to upload EPUBs and track conversion progress. Override defaults by exporting `HOST`, `PORT`, `UVICORN_BIN`, or setting `RELOAD=1` before running.

### 2. Serve your library with Audiobookshelf

Launch the Audiobookshelf Node server in the background:

```bash
./start_audiobookshelf.sh
```

On the first run the script installs dependencies (`npm ci`) and builds the web client (`npm run client`). It then starts `npm start -- --host 0.0.0.0 --port 3333` via `nohup`, logging to `logs/audiobookshelf-<timestamp>.log` and writing the PID to `logs/audiobookshelf.pid`. Visit `http://localhost:3333/audiobookshelf` (or `http://<server-ip>:3333` from other devices) to finish setup.

To stop the service later:

```bash
kill $(cat logs/audiobookshelf.pid)
```

### 3. Connect mobile clients

Find the server’s LAN IP on Linux with:

```bash
hostname -I | awk '{print $1}'
```

Use `http://<that-ip>:3333` as the server URL inside the Audiobookshelf mobile app.

## Repository Notes

- Generated audiobooks are saved under `epubToAudioBook/out/<book-id>/` alongside packaged `.m4b` files and the source EPUB.
- Logs for the TTS generator live in `epubToAudioBook/logs/`; Audiobookshelf runtime logs are stored in `logs/`.
- The repository previously relied on an external shell script to package `.m4b` files; this process is now handled natively by the backend during generation.

---

Enjoy building and listening!
