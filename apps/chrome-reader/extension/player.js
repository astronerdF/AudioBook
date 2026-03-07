/**
 * Chrome Reader - Audio Player
 * Manages audio playback with word-level timing synchronization.
 * Pre-fetches upcoming paragraphs for smoother playback.
 */

window.ChromeReader = window.ChromeReader || {};

ChromeReader.Player = (() => {
  let serverUrl = "http://localhost:8008";
  let voice = "af_heart";
  let speed = 1.0;

  // Playback state
  let paragraphs = [];
  let currentParaIdx = 0;
  let currentSentIdx = 0;
  let currentAudio = null;
  let isPlaying = false;
  let isPaused = false;
  let animFrameId = null;
  let runToken = 0;

  // Callbacks
  let onStateChange = null;
  let onError = null;
  let onStatusUpdate = null;

  const PREFETCH_AHEAD = 2;
  const prefetchCache = new Map(); // paraIdx -> Promise<{sentences, results, paragraph}>

  function emitState() {
    if (onStateChange) onStateChange(getState());
  }

  function emitStatus(message) {
    if (onStatusUpdate) onStatusUpdate(message);
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

  function splitSentences(text) {
    if (typeof Intl !== "undefined" && Intl.Segmenter) {
      try {
        const seg = new Intl.Segmenter("en", { granularity: "sentence" });
        return Array.from(seg.segment(text), (s) => s.segment.trim()).filter(
          (s) => s.length > 0
        );
      } catch (_) {
        // Fallback below.
      }
    }
    return text
      .split(/(?<=[.!?])\s+/)
      .map((p) => p.trim())
      .filter((p) => p.length > 0);
  }

  /**
   * Map each sentence to its start offset in the original paragraph text.
   * Needed because server word offsets are sentence-relative.
   */
  function mapSentenceOffsets(paragraphText, sentences) {
    const offsets = [];
    let cursor = 0;

    for (const sentence of sentences) {
      const idx = paragraphText.indexOf(sentence, cursor);
      const start = idx >= 0 ? idx : cursor;
      offsets.push(start);
      cursor = start + sentence.length;
    }
    return offsets;
  }

  function offsetWords(words, sentenceOffset) {
    if (!Array.isArray(words) || words.length === 0) return [];
    return words.map((w) => ({
      ...w,
      char_start: (w.char_start || 0) + sentenceOffset,
      char_end: (w.char_end || 0) + sentenceOffset,
    }));
  }

  /**
   * Ask background service worker to synthesize a sentence.
   */
  async function synthesizeSentence(text) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage(
        {
          action: "synthesize",
          serverUrl,
          text,
          voice,
        },
        (resp) => {
          if (chrome.runtime.lastError) {
            reject(new Error(chrome.runtime.lastError.message));
            return;
          }
          if (!resp?.ok) {
            if (resp?.error) {
              reject(new Error(resp.error));
            } else if (resp === undefined) {
              reject(new Error("No response from background worker"));
            } else {
              reject(new Error(`Unexpected background response: ${JSON.stringify(resp)}`));
            }
            return;
          }
          resolve(resp.data);
        }
      );
    });
  }

  async function prefetchParagraph(paraIdx, token) {
    if (prefetchCache.has(paraIdx)) return prefetchCache.get(paraIdx);
    if (paraIdx >= paragraphs.length) return null;

    const promise = (async () => {
      const para = paragraphs[paraIdx];
      const sentences = splitSentences(para.text);
      const sentenceOffsets = mapSentenceOffsets(para.text, sentences);
      const results = [];

      for (let si = 0; si < sentences.length; si++) {
        if (!isPlaying || token !== runToken) return null;
        const sentence = sentences[si];

        emitStatus(
          `Synthesizing paragraph ${paraIdx + 1}/${paragraphs.length}, sentence ${si + 1}/${sentences.length}...`
        );

        try {
          const data = await synthesizeSentence(sentence);
          results.push({
            text: sentence,
            sentenceOffset: sentenceOffsets[si] || 0,
            ...data,
          });
        } catch (e) {
          console.error("Chrome Reader: synthesis error", e);
          emitStatus(
            `Error on paragraph ${paraIdx + 1}, sentence ${si + 1}: ${e?.message || "unknown"}`
          );
          results.push({
            text: sentence,
            sentenceOffset: sentenceOffsets[si] || 0,
            error: e.message,
          });
        }
      }

      return { sentences, results, paragraph: para };
    })();

    prefetchCache.set(paraIdx, promise);
    return promise;
  }

  function triggerPrefetch(token) {
    for (
      let i = currentParaIdx;
      i < Math.min(currentParaIdx + PREFETCH_AHEAD, paragraphs.length);
      i++
    ) {
      prefetchParagraph(i, token);
    }
  }

  function playChunk(audioB64, words, textNodes, token) {
    return new Promise((resolve, reject) => {
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

      function tick() {
        if (!isPlaying || isPaused || token !== runToken || audio.paused) return;
        const timeMs = audio.currentTime * 1000;

        let newIdx = -1;
        for (let i = 0; i < words.length; i++) {
          if (timeMs >= words[i].start_ms && timeMs < words[i].end_ms) {
            newIdx = i;
            break;
          }
        }
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
        animFrameId = null;
        ChromeReader.Highlighter.clearWord();
        URL.revokeObjectURL(url);
        currentAudio = null;
        resolve();
      });

      audio.addEventListener("error", () => {
        cancelAnimationFrame(animFrameId);
        animFrameId = null;
        URL.revokeObjectURL(url);
        currentAudio = null;
        reject(new Error("Audio playback error"));
      });

      audio.play().catch(reject);
    });
  }

  async function playLoop(token) {
    let anyPlayed = false;

    while (currentParaIdx < paragraphs.length && isPlaying && token === runToken) {
      const paraData = await prefetchParagraph(currentParaIdx, token);
      if (!paraData || !isPlaying || token !== runToken) break;

      const { results, paragraph } = paraData;
      ChromeReader.Highlighter.highlightSentenceElement(paragraph.element);
      emitStatus(`Reading paragraph ${currentParaIdx + 1}/${paragraphs.length}`);
      triggerPrefetch(token);

      if (!anyPlayed && results.length > 0 && results.every((r) => r.error)) {
        const firstError = results.find((r) => r.error)?.error || "TTS failed";
        const msg = `Cannot reach TTS server: ${firstError}`;
        if (onError) onError(msg);
        stop();
        return;
      }

      for (let sentIdx = 0; sentIdx < results.length && isPlaying && token === runToken; sentIdx++) {
        currentSentIdx = sentIdx;
        emitState();

        const chunk = results[sentIdx];
        if (chunk.error || !chunk.audio_b64) continue;

        try {
          while (isPaused && isPlaying && token === runToken) {
            await new Promise((r) => setTimeout(r, 100));
          }
          if (!isPlaying || token !== runToken) break;

          const shiftedWords = offsetWords(
            chunk.words || [],
            chunk.sentenceOffset || 0
          );
          await playChunk(chunk.audio_b64, shiftedWords, paragraph.textNodes, token);
          anyPlayed = true;
        } catch (e) {
          if (!isPlaying || token !== runToken) break;
          console.error("Chrome Reader: playback error", e);
        }
      }

      if (isPlaying && token === runToken) {
        currentParaIdx++;
        currentSentIdx = 0;
        emitState();
      }
    }

    if (isPlaying && token === runToken) {
      stop();
    }
  }

  function start(extractedParagraphs, settings = {}) {
    stop();

    if (settings.serverUrl) serverUrl = settings.serverUrl;
    if (settings.voice) voice = settings.voice;
    if (settings.speed) speed = settings.speed;

    paragraphs = extractedParagraphs || [];
    currentParaIdx = 0;
    currentSentIdx = 0;
    isPlaying = true;
    isPaused = false;
    runToken++;
    prefetchCache.clear();

    ChromeReader.Highlighter.init();
    emitState();
    emitStatus("Starting synthesis...");
    triggerPrefetch(runToken);
    playLoop(runToken);
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
    runToken++;

    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
    }
    if (animFrameId) {
      cancelAnimationFrame(animFrameId);
      animFrameId = null;
    }

    prefetchCache.clear();
    paragraphs = [];
    currentParaIdx = 0;
    currentSentIdx = 0;
    ChromeReader.Highlighter.clearAll();
    emitState();
  }

  function skipForward() {
    if (!isPlaying) return;
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.dispatchEvent(new Event("ended"));
    }
  }

  function skipBack() {
    if (!isPlaying) return;

    if (currentParaIdx > 0 && currentSentIdx === 0) {
      currentParaIdx = Math.max(0, currentParaIdx - 1);
    }
    currentSentIdx = 0;
    prefetchCache.delete(currentParaIdx);

    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
    }

    runToken++;
    playLoop(runToken);
  }

  function setSpeed(newSpeed) {
    speed = Math.max(0.25, Math.min(4.0, newSpeed));
    if (currentAudio) currentAudio.playbackRate = speed;
    emitState();
  }

  function setVoice(newVoice) {
    voice = newVoice;
    prefetchCache.clear();
    emitState();
  }

  function setOnStateChange(cb) {
    onStateChange = cb;
  }

  function setOnError(cb) {
    onError = cb;
  }

  function setOnStatusUpdate(cb) {
    onStatusUpdate = cb;
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
    setOnError,
    setOnStatusUpdate,
    getState,
    isActive: () => isPlaying,
  };
})();
