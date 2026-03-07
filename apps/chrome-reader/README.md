# Chrome Reader - Kokoro TTS Webpage Reader

Chrome extension that reads any webpage aloud using Kokoro TTS with real-time word-level highlighting.

## Features

- **Smart content extraction** - Readability-inspired algorithm auto-detects the main content on articles, blogs, docs, wikis, forums, and more
- **5 read modes** - Smart (auto), Selection, Visible area, Full page, Headings only
- **Word-level highlighting** - Words light up in sync as they're spoken
- **Auto-scroll** - Page scrolls to follow the reading position
- **5 Kokoro voices** - 3 American (Heart, Bella, Fenrir) + 2 British (Emma, Fable)
- **Speed control** - 0.5x to 3x playback speed
- **Pre-buffering** - Fetches upcoming paragraphs ahead of time for gapless playback
- **Keyboard shortcuts** - Alt+R to play/pause, Alt+S to stop
- **Floating controls** - Minimal in-page control bar while reading
- **Skip code blocks** - Optionally skip `<pre>` and `<code>` elements
- **Works on any HTTP/HTTPS page**

## Architecture

```
Webpage ──> Content Script (extractor.js + highlighter.js + player.js + content.js)
              │
              │ fetch (sentences, one at a time, pre-buffered)
              ▼
            TTS Server (FastAPI + Kokoro 82M, port 8008)
              │
              │ returns WAV audio + word-level timing estimates
              ▼
            Content Script plays audio via Audio element
              │
              │ requestAnimationFrame loop matches word timings
              ▼
            Highlight overlay positions over current word in DOM
```

## Setup

### 1. Start the TTS Server

Requires the same Python venv as epubToAudioBook (torch + kokoro already installed):

```bash
cd apps/chrome-reader/server
./start_server.sh
```

Or manually:
```bash
export KOKORO_DEVICE=cuda:0  # or cpu
python tts_server.py
```

Server runs on port 8008 by default. Set `PORT` env var to change.

### 2. Load the Chrome Extension

1. Open Chrome and go to `chrome://extensions/`
2. Enable **Developer mode** (top right toggle)
3. Click **Load unpacked**
4. Select the `apps/chrome-reader/extension/` directory
5. The Chrome Reader icon appears in the toolbar

### 3. Use It

1. Navigate to any webpage
2. Click the Chrome Reader icon in the toolbar
3. Choose a read mode (Smart is default)
4. Click the play button
5. The page starts reading aloud with word highlighting

## Read Modes

| Mode | Best for | How it works |
|------|----------|--------------|
| **Smart** | Articles, blogs, news, docs | Scores DOM elements by text density, semantic tags, class names. Picks the best content root. |
| **Selection** | Reading a specific paragraph | Reads only the text you've selected on the page. Falls back to Smart if nothing selected. |
| **Visible** | Skimming the current view | Reads only paragraphs currently visible in the viewport. |
| **Full page** | Dense or unconventional layouts | Reads everything on the page (with filtering of scripts, nav, etc). |
| **Headings** | Quick page summary | Reads only h1-h6 headings for a fast overview. |

## Smart Extraction Details

The extractor handles various page types:

- **News/Articles** - Detects `<article>`, `.post-content`, `.entry-content`, `.article-body`
- **Documentation** - Finds `.markdown-body`, `.s-prose`, main content areas
- **Wikipedia** - Uses `#mw-content-text`
- **Blogs/CMS** - Scores by paragraph density and text-to-HTML ratio
- **Generic pages** - Falls back to Readability-style scoring (text density, link density, class/ID hints)

## Server API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Server status + model info |
| `/voices` | GET | List available Kokoro voices |
| `/synthesize` | POST | Synthesize text, returns `{audio_b64, words, duration_ms}` |
| `/synthesize/stream` | POST | SSE stream: synthesizes text sentence-by-sentence |

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Alt+R | Play / Pause |
| Alt+S | Stop |

Configurable in `chrome://extensions/shortcuts`.

## Configuration

All settings persist in Chrome's local storage:
- **Server URL** - Default `http://localhost:8008`
- **Voice** - Default `af_heart` (Heart, female, American)
- **Speed** - Default 1.0x (range 0.5-3.0)
- **Skip code** - Skip `<pre>` blocks (default: on)
- **Auto-scroll** - Scroll page to follow reading (default: on)
- **Highlight** - Show word highlight overlay (default: on)

## Regenerating Icons

```bash
cd apps/chrome-reader/extension/icons
python generate_icons.py
```

Generates 16x16, 32x32, 48x48, and 128x128 PNG icons.
