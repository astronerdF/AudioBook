# Chrome Reader - Kokoro TTS Webpage Reader

Chrome extension that reads any webpage aloud using Kokoro TTS with real-time word-level highlighting.

## Features

- **Smart content extraction** - Readability-inspired algorithm auto-detects the main content on articles, blogs, docs, wikis, forums, and more
- **5 read modes** - Smart (auto), Selection, Visible area, Full page, Headings only
- **Word-level highlighting** - Words light up in sync as they're spoken
- **Auto-scroll** - Page scrolls to follow the reading position
- **5 Kokoro voices** - 3 American (Heart, Bella, Fenrir) + 2 British (Emma, Fable)
- **Selectable inference path** - Run fully on-device or switch back to a localhost Kokoro server
- **Auto backend selection** - Uses WebGPU when available, falls back to CPU/WASM automatically
- **Speed control** - 0.5x to 3x playback speed
- **Chunked synthesis** - Generates sentence-by-sentence and only prefetches nearby paragraphs
- **Keyboard shortcuts** - Alt+R to play/pause, Alt+S to stop
- **Floating controls** - Minimal in-page control bar while reading
- **Skip code blocks** - Optionally skip `<pre>` and `<code>` elements
- **Works on any HTTP/HTTPS page**

## Architecture

```
Webpage ──> Content Script (extractor.js + highlighter.js + tts-engine.js + player.js + content.js)
              │
              │ sentence-sized jobs
              ▼
            Module Worker (tts-worker.mjs)
              │
              │ packaged Kokoro ONNX + voice embeddings
              │ packaged HeadTTS English G2P + ONNX Runtime Web
              ▼
            WebGPU (preferred) or WASM/CPU fallback
              │
              │ returns WAV audio + local word timing estimates
              ▼
            Content Script plays audio via Audio element
              │
              │ requestAnimationFrame loop matches word timings
              ▼
            Highlight overlay positions over current word in DOM
```

## Setup

### 1. Load the Chrome Extension

1. Open Chrome and go to `chrome://extensions/`
2. Enable **Developer mode** (top right toggle)
3. Click **Load unpacked**
4. Select the `apps/chrome-reader/extension/` directory
5. The Chrome Reader icon appears in the toolbar

### 2. Use It

1. Navigate to any webpage
2. Click the Chrome Reader icon in the toolbar
3. Choose a read mode (Smart is default)
4. Click the play button
5. The page starts reading aloud with word highlighting

The extension can run in two modes:

- **On-device** - Loads the packaged model lazily on first playback. On machines with WebGPU support it uses the GPU; otherwise it falls back to CPU/WASM automatically.
- **Localhost server** - Sends synthesis requests to a Kokoro server at `http://localhost:8008` or `http://127.0.0.1:8008`.

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

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Alt+R | Play / Pause |
| Alt+S | Stop |

Configurable in `chrome://extensions/shortcuts`.

## Configuration

All settings persist in Chrome's local storage:
- **Voice** - Default `af_heart` (Heart, female, American)
- **Speed** - Default 1.0x (range 0.5-3.0)
- **Skip code** - Skip `<pre>` blocks (default: on)
- **Auto-scroll** - Scroll page to follow reading (default: on)
- **Highlight** - Show word highlight overlay (default: on)

## Notes

- The packaged extension can run fully without the Python server in `apps/chrome-reader/server/`.
- Server mode is optional and can be re-enabled from the popup when your laptop is too slow for on-device inference.
- Sentence-sized synthesis keeps startup latency low and avoids generating audio far ahead on long pages.

## Regenerating Icons

```bash
cd apps/chrome-reader/extension/icons
python generate_icons.py
```

Generates 16x16, 32x32, 48x48, and 128x128 PNG icons.
