/**
 * Chrome Reader - Audio Player
 * Manages Kokoro playback with sentence-level synthesis and nearby prefetching.
 */

window.ChromeReader = window.ChromeReader || {};

ChromeReader.Player = (() => {
  let voice = "af_heart";
  let speed = 1.0;

  let paragraphs = [];
  let currentParaIdx = 0;
  let currentSentIdx = 0;
  let currentSource = null;   // AudioBufferSourceNode
  let currentAudio = null;    // kept for skipForward compat
  let audioCtx = null;
  let isPlaying = false;
  let isPaused = false;
  let animFrameId = null;
  let runToken = 0;
  let engineStatus = ChromeReader.TtsEngine.getStatus();

  let onStateChange = null;
  let onError = null;
  let onStatusUpdate = null;

  const PREFETCH_PIXEL_DISTANCE = 2400;
  const prefetchCache = new Map();

  function createDeferred() {
    let resolve;
    return {
      resolved: false,
      promise: new Promise((res) => {
        resolve = res;
      }),
      resolve(value) {
        if (this.resolved) return;
        this.resolved = true;
        resolve(value);
      },
    };
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

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
      engine: { ...engineStatus },
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

  async function synthesizeSentence(text) {
    return ChromeReader.TtsEngine.synthesize(text, { voice });
  }

  function paragraphDistancePx(fromIdx, toIdx) {
    const fromEl = paragraphs[fromIdx]?.element;
    const toEl = paragraphs[toIdx]?.element;
    if (!fromEl || !toEl) return 0;

    const fromTop = fromEl.getBoundingClientRect().top + window.scrollY;
    const toTop = toEl.getBoundingClientRect().top + window.scrollY;
    return Math.max(0, toTop - fromTop);
  }

  function shouldPrefetchParagraph(paraIdx) {
    if (paraIdx < currentParaIdx || paraIdx >= paragraphs.length) return false;
    if (paraIdx === currentParaIdx) return true;
    return paragraphDistancePx(currentParaIdx, paraIdx) <= PREFETCH_PIXEL_DISTANCE;
  }

  function createParagraphTask(paraIdx, token) {
    const para = paragraphs[paraIdx];
    const sentences = splitSentences(para.text);
    const sentenceOffsets = mapSentenceOffsets(para.text, sentences);
    const slots = sentences.map(() => createDeferred());

    const task = {
      paragraph: para,
      sentences,
      results: new Array(sentences.length).fill(null),
      lastError: null,
      done: false,
      waitForSentence(sentIdx) {
        const slot = slots[sentIdx];
        return slot ? slot.promise : Promise.resolve(null);
      },
    };

    (async () => {
      for (let sentIdx = 0; sentIdx < sentences.length; sentIdx++) {
        if (!isPlaying || token !== runToken) break;

        const sentence = sentences[sentIdx];
        emitStatus(
        `Synthesizing paragraph ${paraIdx + 1}/${paragraphs.length}, sentence ${sentIdx + 1}/${sentences.length}...`
        );

        let result = null;
        try {
          const data = await synthesizeSentence(sentence);
          result = {
            text: sentence,
            sentenceOffset: sentenceOffsets[sentIdx] || 0,
            ...data,
          };
        } catch (error) {
          result = {
            text: sentence,
            sentenceOffset: sentenceOffsets[sentIdx] || 0,
            error: error?.message || "Synthesis failed",
          };
          task.lastError = result.error;
          console.error("Chrome Reader: synthesis error", error);
        }

        task.results[sentIdx] = result;
        slots[sentIdx].resolve(result);
      }

      task.done = true;
      slots.forEach((slot) => slot.resolve(null));
    })();

    return task;
  }

  function ensureParagraphTask(paraIdx, token) {
    if (!shouldPrefetchParagraph(paraIdx)) return null;
    if (prefetchCache.has(paraIdx)) return prefetchCache.get(paraIdx);
    const task = createParagraphTask(paraIdx, token);
    prefetchCache.set(paraIdx, task);
    return task;
  }

  function triggerPrefetch(token) {
    const currentTask = ensureParagraphTask(currentParaIdx, token);
    if (!currentTask) return;

    const nearParagraphEnd =
      currentTask.sentences.length <= 2 ||
      currentSentIdx >= Math.max(0, currentTask.sentences.length - 2);

    if (!nearParagraphEnd) return;

    const nextParaIdx = currentParaIdx + 1;
    if (shouldPrefetchParagraph(nextParaIdx)) {
      ensureParagraphTask(nextParaIdx, token);
    }
  }

  function getAudioCtx() {
    if (!audioCtx || audioCtx.state === "closed") {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    return audioCtx;
  }

  async function playChunk(audioBuffer, words, textNodes, token) {
    const ctx = getAudioCtx();

    // Resume AudioContext if suspended (autoplay policy unlock).
    if (ctx.state === "suspended") {
      await ctx.resume();
    }

    return new Promise((resolve, reject) => {
      const blob = new Blob([audioBuffer], { type: "audio/wav" });
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);

      // Preserve pitch when changing playback speed.
      audio.preservesPitch = true;
      audio.mozPreservePitch = true;
      audio.playbackRate = speed;

      // Route through the AudioContext — this bypasses the autoplay restriction
      // that blocks audio.play() in content scripts driven by extension messages.
      const mediaSource = ctx.createMediaElementSource(audio);
      mediaSource.connect(ctx.destination);

      currentSource = mediaSource;
      currentAudio = audio;
      let currentWordIdx = -1;

      function cleanup() {
        cancelAnimationFrame(animFrameId);
        animFrameId = null;
        URL.revokeObjectURL(url);
        currentSource = null;
        currentAudio = null;
      }

      function tick() {
        if (!isPlaying || isPaused || token !== runToken || audio.paused) return;
        // audio.currentTime reflects position in the audio file, accounting for playbackRate.
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
        cleanup();
        ChromeReader.Highlighter.clearWord();
        resolve();
      });

      audio.addEventListener("error", () => {
        cleanup();
        reject(new Error("Audio playback error"));
      });

      audio.play().catch((error) => {
        cleanup();
        reject(error);
      });
    });
  }

  async function playLoop(token) {
    let anyPlayed = false;

    while (currentParaIdx < paragraphs.length && isPlaying && token === runToken) {
      const task = ensureParagraphTask(currentParaIdx, token);
      if (!task) break;

      const { paragraph, sentences } = task;
      let paragraphPlayed = false;

      ChromeReader.Highlighter.highlightSentenceElement(paragraph.element);
      emitStatus(
        `Reading paragraph ${currentParaIdx + 1}/${paragraphs.length} on ${engineStatus.deviceLabel || "local inference"}`
      );
      triggerPrefetch(token);

      for (let sentIdx = 0; sentIdx < sentences.length && isPlaying && token === runToken; sentIdx++) {
        currentSentIdx = sentIdx;
        emitState();
        triggerPrefetch(token);

        const chunk = await task.waitForSentence(sentIdx);
        if (!isPlaying || token !== runToken) break;
        if (!chunk) continue;
        if (chunk.error || !chunk.audio) continue;

        while (isPaused && isPlaying && token === runToken) {
          await sleep(100);
        }
        if (!isPlaying || token !== runToken) break;

        try {
          const shiftedWords = offsetWords(chunk.words || [], chunk.sentenceOffset || 0);
          await playChunk(chunk.audio, shiftedWords, paragraph.textNodes, token);
          paragraphPlayed = true;
          anyPlayed = true;
          triggerPrefetch(token);
        } catch (error) {
          if (!isPlaying || token !== runToken) break;
          console.error("Chrome Reader: playback error", error);
        }
      }

      if (!paragraphPlayed && task.lastError && !anyPlayed) {
          if (onError) {
          onError(`Kokoro synthesis failed: ${task.lastError}`);
        }
        stop();
        return;
      }

      if (isPlaying && token === runToken) {
        const completedIdx = currentParaIdx;
        currentParaIdx++;
        currentSentIdx = 0;
        prefetchCache.delete(completedIdx);
        emitState();
      }
    }

    if (isPlaying && token === runToken) {
      stop();
    }
  }

  async function start(extractedParagraphs, settings = {}) {
    stop();

    if (settings.voice) voice = settings.voice;
    if (settings.speed) speed = settings.speed;
    ChromeReader.TtsEngine.configure({
      transport: settings.transport,
      serverUrl: settings.serverUrl,
    });
    engineStatus = ChromeReader.TtsEngine.getStatus();

    paragraphs = extractedParagraphs || [];
    currentParaIdx = 0;
    currentSentIdx = 0;
    isPlaying = true;
    isPaused = false;
    runToken++;
    prefetchCache.clear();

    ChromeReader.TtsEngine.setOnStatusChange((status) => {
      engineStatus = status;
      emitState();
    });

    ChromeReader.Highlighter.init();
    emitState();
    emitStatus(engineStatus.message || "Preparing Kokoro engine...");

    const token = runToken;
    try {
      await ChromeReader.TtsEngine.initialize();
    } catch (error) {
      if (isPlaying && token === runToken) {
        if (onError) {
          onError(`Kokoro engine failed: ${error.message}`);
        }
        stop();
      }
      return;
    }

    if (!isPlaying || token !== runToken) return;

    triggerPrefetch(token);
    playLoop(token);
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
    if (currentAudio) currentAudio.play().catch(() => {});
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

    ChromeReader.TtsEngine.cancelPending();

    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
    }
    currentSource = null;
    if (audioCtx) {
      audioCtx.close().catch(() => {});
      audioCtx = null;
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
    if (!isPlaying || !currentAudio) return;
    currentAudio.pause();
    currentAudio.dispatchEvent(new Event("ended"));
  }

  function skipBack() {
    if (!isPlaying) return;

    if (currentParaIdx > 0 && currentSentIdx === 0) {
      currentParaIdx = Math.max(0, currentParaIdx - 1);
    }
    currentSentIdx = 0;

    prefetchCache.delete(currentParaIdx);
    ChromeReader.TtsEngine.cancelPending();

    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
    }
    currentSource = null;

    runToken++;
    triggerPrefetch(runToken);
    playLoop(runToken);
  }

  function setSpeed(newSpeed) {
    speed = Math.max(0.25, Math.min(4.0, newSpeed));
    if (currentAudio) currentAudio.playbackRate = speed;
    emitState();
  }

  function setVoice(newVoice) {
    voice = newVoice;
    emitState();
  }

  function updateEngineSettings(settings = {}) {
    ChromeReader.TtsEngine.configure({
      transport: settings.transport,
      serverUrl: settings.serverUrl,
    });
    engineStatus = ChromeReader.TtsEngine.getStatus();
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
    updateEngineSettings,
    setOnStateChange,
    setOnError,
    setOnStatusUpdate,
    getState,
    isActive: () => isPlaying,
  };
})();
