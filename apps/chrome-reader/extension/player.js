/**
 * Chrome Reader - Audio Player
 * Manages audio playback with word-level timing synchronization.
 * Uses Audio elements for simple, reliable playback with speed control.
 * Pre-fetches upcoming paragraphs for gapless playback.
 */

window.ChromeReader = window.ChromeReader || {};

ChromeReader.Player = (() => {
  let serverUrl = "http://localhost:8008";
  let voice = "af_heart";
  let speed = 1.0;

  // Playback state
  let paragraphs = [];       // Array of extracted paragraphs
  let currentParaIdx = 0;
  let currentSentences = []; // Current paragraph split into sentences
  let currentSentIdx = 0;
  let audioQueue = [];       // Pre-fetched audio data
  let currentAudio = null;   // Currently playing Audio element
  let isPlaying = false;
  let isPaused = false;
  let animFrameId = null;
  let onStateChange = null;  // Callback for state updates
  let abortController = null;

  // Pre-fetch buffer
  const PREFETCH_AHEAD = 2;  // Paragraphs to pre-fetch
  const prefetchCache = new Map(); // paraIdx -> Promise<sentences data>

  /**
   * Split text into sentences using Intl.Segmenter if available, else regex.
   */
  function splitSentences(text) {
    if (typeof Intl !== "undefined" && Intl.Segmenter) {
      try {
        const seg = new Intl.Segmenter("en", { granularity: "sentence" });
        return Array.from(seg.segment(text), (s) => s.segment.trim()).filter(
          (s) => s.length > 0
        );
      } catch (_) {
        // Fallback
      }
    }
    // Regex fallback
    const parts = text.split(/(?<=[.!?])\s+/);
    return parts.map((p) => p.trim()).filter((p) => p.length > 0);
  }

  /**
   * Fetch audio for a single sentence from the TTS server.
   */
  async function synthesizeSentence(text, signal) {
    const resp = await fetch(`${serverUrl}/synthesize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice }),
      signal,
    });
    if (!resp.ok) {
      throw new Error(`TTS server error: ${resp.status}`);
    }
    return resp.json();
  }

  /**
   * Pre-fetch all sentences for a paragraph.
   */
  async function prefetchParagraph(paraIdx) {
    if (prefetchCache.has(paraIdx)) return prefetchCache.get(paraIdx);
    if (paraIdx >= paragraphs.length) return null;

    const promise = (async () => {
      const para = paragraphs[paraIdx];
      const sentences = splitSentences(para.text);
      const results = [];

      for (const sentence of sentences) {
        if (abortController?.signal.aborted) return null;
        try {
          const data = await synthesizeSentence(sentence, abortController?.signal);
          results.push({ text: sentence, ...data });
        } catch (e) {
          if (e.name === "AbortError") return null;
          console.error("Chrome Reader: synthesis error", e);
          results.push({ text: sentence, error: e.message });
        }
      }
      return { sentences, results, paragraph: para };
    })();

    prefetchCache.set(paraIdx, promise);
    return promise;
  }

  /**
   * Start pre-fetching upcoming paragraphs.
   */
  function triggerPrefetch() {
    for (let i = currentParaIdx; i < Math.min(currentParaIdx + PREFETCH_AHEAD, paragraphs.length); i++) {
      prefetchParagraph(i);
    }
  }

  /**
   * Play a single audio chunk with word highlighting.
   * Returns a promise that resolves when playback finishes.
   */
  function playChunk(audioB64, words, textNodes) {
    return new Promise((resolve, reject) => {
      // Decode base64 WAV to blob URL
      const binary = atob(audioB64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
      }
      const blob = new Blob([bytes], { type: "audio/wav" });
      const url = URL.createObjectURL(blob);

      const audio = new Audio(url);
      audio.playbackRate = speed;
      currentAudio = audio;

      let currentWordIdx = -1;

      // Word highlighting loop
      function tick() {
        if (!isPlaying || audio.paused) return;
        const timeMs = audio.currentTime * 1000;

        // Find current word
        let newIdx = -1;
        for (let i = 0; i < words.length; i++) {
          if (timeMs >= words[i].start_ms && timeMs < words[i].end_ms) {
            newIdx = i;
            break;
          }
        }
        // If past all words, highlight last word
        if (newIdx === -1 && words.length > 0 && timeMs >= words[words.length - 1].start_ms) {
          newIdx = words.length - 1;
        }

        if (newIdx !== currentWordIdx && newIdx >= 0) {
          currentWordIdx = newIdx;
          ChromeReader.Highlighter.highlightWord(textNodes, words[newIdx]);
        }

        animFrameId = requestAnimationFrame(tick);
      }

      audio.addEventListener("play", () => {
        animFrameId = requestAnimationFrame(tick);
      });

      audio.addEventListener("ended", () => {
        cancelAnimationFrame(animFrameId);
        ChromeReader.Highlighter.clearWord();
        URL.revokeObjectURL(url);
        currentAudio = null;
        resolve();
      });

      audio.addEventListener("error", (e) => {
        cancelAnimationFrame(animFrameId);
        URL.revokeObjectURL(url);
        currentAudio = null;
        reject(new Error("Audio playback error"));
      });

      audio.play().catch(reject);
    });
  }

  /**
   * Play through all paragraphs sequentially.
   */
  async function playLoop() {
    while (currentParaIdx < paragraphs.length && isPlaying) {
      const paraData = await prefetchParagraph(currentParaIdx);
      if (!paraData || !isPlaying) break;

      const { results, paragraph } = paraData;
      ChromeReader.Highlighter.highlightSentenceElement(paragraph.element);

      // Trigger pre-fetch for next paragraphs
      triggerPrefetch();

      for (let sentIdx = 0; sentIdx < results.length && isPlaying; sentIdx++) {
        currentSentIdx = sentIdx;
        emitState();

        const chunk = results[sentIdx];
        if (chunk.error || !chunk.audio_b64) continue;

        try {
          // Wait if paused
          while (isPaused && isPlaying) {
            await new Promise((r) => setTimeout(r, 100));
          }
          if (!isPlaying) break;

          await playChunk(chunk.audio_b64, chunk.words || [], paragraph.textNodes);
        } catch (e) {
          if (!isPlaying) break;
          console.error("Chrome Reader: playback error", e);
        }
      }

      if (isPlaying) {
        currentParaIdx++;
        currentSentIdx = 0;
        emitState();
      }
    }

    // Finished all paragraphs
    if (isPlaying) {
      stop();
    }
  }

  /**
   * Emit current state for popup updates.
   */
  function emitState() {
    if (onStateChange) {
      onStateChange(getState());
    }
  }

  function getState() {
    return {
      isPlaying,
      isPaused,
      currentParaIdx,
      currentSentIdx,
      totalParagraphs: paragraphs.length,
      voice,
      speed,
    };
  }

  // --- Public API ---

  function start(extractedParagraphs, settings = {}) {
    stop(); // Clean up any previous session

    if (settings.serverUrl) serverUrl = settings.serverUrl;
    if (settings.voice) voice = settings.voice;
    if (settings.speed) speed = settings.speed;

    paragraphs = extractedParagraphs;
    currentParaIdx = 0;
    currentSentIdx = 0;
    isPlaying = true;
    isPaused = false;
    abortController = new AbortController();
    prefetchCache.clear();

    ChromeReader.Highlighter.init();
    emitState();
    triggerPrefetch();
    playLoop();
  }

  function pause() {
    if (!isPlaying) return;
    isPaused = true;
    if (currentAudio) currentAudio.pause();
    emitState();
  }

  function resume() {
    if (!isPlaying) return;
    isPaused = false;
    if (currentAudio) currentAudio.play();
    emitState();
  }

  function toggle() {
    if (!isPlaying) return;
    if (isPaused) resume();
    else pause();
  }

  function stop() {
    isPlaying = false;
    isPaused = false;
    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
    }
    if (animFrameId) {
      cancelAnimationFrame(animFrameId);
      animFrameId = null;
    }
    if (abortController) {
      abortController.abort();
      abortController = null;
    }
    prefetchCache.clear();
    paragraphs = [];
    ChromeReader.Highlighter.clearAll();
    emitState();
  }

  function skipForward() {
    if (!isPlaying) return;
    // Skip to next paragraph
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.dispatchEvent(new Event("ended"));
    }
  }

  function skipBack() {
    if (!isPlaying) return;
    // Go back to start of current paragraph (or previous if at start)
    if (currentParaIdx > 0 && currentSentIdx === 0) {
      currentParaIdx = Math.max(0, currentParaIdx - 1);
    }
    currentSentIdx = 0;
    prefetchCache.delete(currentParaIdx);

    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
    }
    // Restart playback from current position
    playLoop();
  }

  function setSpeed(newSpeed) {
    speed = Math.max(0.25, Math.min(4.0, newSpeed));
    if (currentAudio) currentAudio.playbackRate = speed;
    emitState();
  }

  function setVoice(newVoice) {
    voice = newVoice;
    // Clear prefetch cache since voice changed
    prefetchCache.clear();
    emitState();
  }

  function setOnStateChange(cb) {
    onStateChange = cb;
  }

  return {
    start,
    pause,
    resume,
    toggle,
    stop,
    skipForward,
    skipBack,
    setSpeed,
    setVoice,
    setOnStateChange,
    getState,
    isActive: () => isPlaying,
  };
})();
