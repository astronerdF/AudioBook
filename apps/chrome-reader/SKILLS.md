# Chrome Reader - Development Skills

## Quick Reference

### Loading the Extension
1. `chrome://extensions/` -> Developer mode -> Load unpacked
2. Select `apps/chrome-reader/extension/`

## Architecture Decisions

### Why TTS runs inside an extension worker
The extension now ships with the Kokoro ONNX model, selected voice embeddings, HeadTTS English G2P, and ONNX Runtime Web. A dedicated module worker keeps inference off the page thread and removes the localhost dependency entirely.

### Why WebGPU first, WASM second
WebGPU gives the best latency on supported machines. WASM keeps the extension portable across laptops and operating systems when GPU inference is unavailable.

### Why heuristic word timing (not WhisperX alignment)
The packaged ONNX model returns audio but not aligned word timestamps. The extension estimates word timings locally so highlighting stays responsive without adding an alignment model.

### Why overlay-based highlighting (not DOM modification)
Wrapping words in `<mark>` elements modifies the page DOM, which can break page scripts, layouts, and our own text node mappings. Positioned overlay divs are non-destructive, performant, and work on any page.

### Why sentence-level chunking (not paragraph-level)
Shorter text produces faster synthesis. The user hears the first sentence ~200-500ms after clicking play. Paragraph-level would delay start by seconds for long paragraphs.

### Why nearby-only prefetching
The player now preloads only the current paragraph and, near the paragraph boundary, the next nearby paragraph. This avoids wasting synthesis work on content far ahead in long pages.

## File Map

| File | Purpose |
|------|---------|
| `extension/manifest.json` | MV3 manifest for the packaged serverless extension |
| `extension/background.js` | Service worker - keyboard shortcuts and settings CRUD |
| `extension/extractor.js` | Smart DOM content extraction with Readability-style scoring |
| `extension/highlighter.js` | Positioned overlay divs for word/sentence highlighting |
| `extension/tts-engine.js` | Content-side bridge to the local inference worker |
| `extension/tts-worker.mjs` | Module worker running ONNX inference locally |
| `extension/player.js` | Audio playback queue with sentence streaming and nearby prefetching |
| `extension/content.js` | Coordinator - ties modules together, handles popup messages |
| `extension/popup.html/css/js` | Popup UI - transport controls, local engine status, voice/speed/mode selection |
| `extension/content.css` | Highlight overlay and floating controls bar styles |
| `extension/models/kokoro/` | Packaged ONNX model, tokenizer metadata, and selected voices |
| `extension/vendor/` | Vendored ONNX Runtime Web and HeadTTS language assets |

## Common Modifications

### Adding a new voice
1. Extract the voice embedding from `apps/KokoroAndroid/app/src/main/assets/voices.bin`
2. Add the resulting `.bin` under `extension/models/kokoro/voices/`
2. Add `<option>` to `popup.html` voice selector

### Adding a new read mode
1. Add extraction logic in `extractor.js` `extract()` function
2. Add `<option>` to `popup.html` mode selector

### Adding a site-specific selector
Add CSS selector string to `SITE_SELECTORS` array in `extractor.js`.

### Changing highlight style
Modify `.cr-word-highlight` in `content.css` (background color, border-radius, shadow).

### Adjusting pre-fetch depth
Adjust the nearby prefetch logic in `player.js` (`PREFETCH_PIXEL_DISTANCE` and `triggerPrefetch()`).
