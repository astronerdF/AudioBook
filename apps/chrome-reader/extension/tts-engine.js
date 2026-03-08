/**
 * Chrome Reader - Local TTS bridge
 * Loads the packaged Kokoro runtime directly in the isolated content script.
 */

window.ChromeReader = window.ChromeReader || {};

ChromeReader.TtsEngine = (() => {
  const DEFAULT_STATUS = {
    ready: false,
    status: "idle",
    device: "uninitialized",
    deviceLabel: "Not loaded",
    message: "Local Kokoro loads on first play",
    error: null,
  };

  let initPromise = null;
  let runtimePromise = null;
  let unsubscribeRuntime = null;
  let status = { ...DEFAULT_STATUS };
  const listeners = new Set();

  function emitStatus() {
    const snapshot = getStatus();
    for (const listener of listeners) {
      try {
        listener(snapshot);
      } catch (_) {
        // Listener failures should not break playback.
      }
    }
  }

  function applyStatus(partial) {
    if (!partial) return;
    status = {
      ...status,
      ...partial,
      error:
        partial.status === "error"
          ? partial.error || partial.message || status.error
          : partial.error ?? null,
    };
    emitStatus();
  }

  async function getRuntime() {
    if (!runtimePromise) {
      runtimePromise = import(chrome.runtime.getURL("tts-runtime.mjs"))
        .then((runtime) => {
          if (!unsubscribeRuntime && runtime.subscribe) {
            unsubscribeRuntime = runtime.subscribe((nextStatus) => {
              applyStatus(nextStatus);
            });
          }
          return runtime;
        })
        .catch((error) => {
          runtimePromise = null;
          applyStatus({
            ready: false,
            status: "error",
            message: error.message,
            error: error.message,
          });
          throw error;
        });
    }

    return runtimePromise;
  }

  function decodeBase64ToArrayBuffer(base64) {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
  }

  async function initialize() {
    if (status.ready) return getStatus();
    if (initPromise) return initPromise;

    applyStatus({
      ready: false,
      status: "loading",
      message: "Preparing local Kokoro engine...",
      error: null,
    });

    initPromise = getRuntime()
      .then((runtime) => runtime.initialize())
      .then((data) => {
        applyStatus({
          ...data,
          ready: true,
          status: "ready",
          error: null,
          message: data?.message || "Local Kokoro ready",
        });
        return getStatus();
      })
      .catch((error) => {
        applyStatus({
          ready: false,
          status: "error",
          message: error.message,
          error: error.message,
        });
        throw error;
      })
      .finally(() => {
        initPromise = null;
      });

    return initPromise;
  }

  async function synthesize(text, options = {}) {
    const cleanText = (text || "").trim();
    if (!cleanText) {
      throw new Error("Empty text");
    }

    await initialize();
    const runtime = await getRuntime();
    return runtime.synthesize(cleanText, options.voice || "af_heart");
  }

  function cancelPending() {
    getRuntime()
      .then((runtime) => runtime.cancelAll())
      .catch(() => {});
  }

  function getStatus() {
    return { ...status };
  }

  function setOnStatusChange(listener) {
    listeners.clear();
    if (listener) {
      listeners.add(listener);
      listener(getStatus());
    }
  }

  return {
    initialize,
    synthesize,
    cancelPending,
    getStatus,
    setOnStatusChange,
  };
})();
