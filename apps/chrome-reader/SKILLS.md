# Chrome Reader - Development Skills

## Quick Reference

### Running the TTS Server
```bash
# GPU (default)
KOKORO_DEVICE=cuda:0 python apps/chrome-reader/server/tts_server.py

# CPU
KOKORO_DEVICE=cpu python apps/chrome-reader/server/tts_server.py

# Custom port
PORT=9000 python apps/chrome-reader/server/tts_server.py
```

### Testing the Server
```bash
# Health check
curl http://localhost:8008/health

# List voices
curl http://localhost:8008/voices

# Synthesize text
curl -X POST http://localhost:8008/synthesize \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world, this is a test.", "voice": "af_heart"}'
```

### Loading the Extension
1. `chrome://extensions/` -> Developer mode -> Load unpacked
2. Select `apps/chrome-reader/extension/`

## Architecture Decisions

### Why content script fetches directly (not via background)
Content scripts can make cross-origin requests to URLs in `host_permissions` (Chrome 101+). This avoids the overhead of routing every TTS request through the background service worker. The background only handles settings storage and keyboard shortcuts.

### Why heuristic word timing (not WhisperX alignment)
WhisperX alignment adds 2-5s latency per sentence, unacceptable for real-time reading. The heuristic approach (proportional distribution by character length with punctuation pause weights) is instantaneous and accurate enough for highlighting purposes.

### Why overlay-based highlighting (not DOM modification)
Wrapping words in `<mark>` elements modifies the page DOM, which can break page scripts, layouts, and our own text node mappings. Positioned overlay divs are non-destructive, performant, and work on any page.

### Why pre-fetch 2 paragraphs ahead
Kokoro synthesis takes ~200ms per second of audio (RTF ~0.2). A typical sentence produces 2-4s of audio. Pre-fetching 2 paragraphs ahead ensures the next audio is always buffered before the current one finishes.

### Why sentence-level chunking (not paragraph-level)
Shorter text produces faster synthesis. The user hears the first sentence ~200-500ms after clicking play. Paragraph-level would delay start by seconds for long paragraphs.

## File Map

| File | Purpose |
|------|---------|
| `server/tts_server.py` | FastAPI server wrapping Kokoro TTS with /synthesize and /synthesize/stream endpoints |
| `extension/manifest.json` | MV3 manifest with host_permissions for localhost:8008 |
| `extension/background.js` | Service worker - keyboard shortcuts, settings CRUD, server health |
| `extension/extractor.js` | Smart DOM content extraction with Readability-style scoring |
| `extension/highlighter.js` | Positioned overlay divs for word/sentence highlighting |
| `extension/player.js` | Audio playback queue with pre-fetching and speed control |
| `extension/content.js` | Coordinator - ties modules together, handles popup messages |
| `extension/popup.html/css/js` | Popup UI - transport controls, voice/speed/mode selection |
| `extension/content.css` | Highlight overlay and floating controls bar styles |

## Common Modifications

### Adding a new voice
1. Add voice metadata to `VOICES` list in `server/tts_server.py`
2. Add `<option>` to `popup.html` voice selector

### Adding a new read mode
1. Add extraction logic in `extractor.js` `extract()` function
2. Add `<option>` to `popup.html` mode selector

### Adding a site-specific selector
Add CSS selector string to `SITE_SELECTORS` array in `extractor.js`.

### Changing highlight style
Modify `.cr-word-highlight` in `content.css` (background color, border-radius, shadow).

### Adjusting pre-fetch depth
Change `PREFETCH_AHEAD` constant in `player.js`.
