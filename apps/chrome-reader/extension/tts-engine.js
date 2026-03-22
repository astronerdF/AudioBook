/**
 * Chrome Reader - TTS bridge
 * Switches between packaged on-device Kokoro and a localhost server.
 */

window.ChromeReader = window.ChromeReader || {};

ChromeReader.TtsEngine = (() => {
  const DEFAULT_CONFIG = {
    transport: "local",
    serverUrl: "http://localhost:8008",
  };

  const LOCAL_STATUS = {
    ready: false,
    status: "idle",
    device: "uninitialized",
    deviceLabel: "On-device",
    message: "On-device Kokoro loads on first play",
    error: null,
  };

  let initPromise = null;
  let runtimePromise = null;
  let unsubscribeRuntime = null;
  let config = { ...DEFAULT_CONFIG };
  let status = buildIdleStatus(config);
  const listeners = new Set();

  function normalizeTransport(transport) {
    return transport === "server" ? "server" : "local";
  }

  function normalizeServerUrl(serverUrl) {
    return (serverUrl || DEFAULT_CONFIG.serverUrl).trim().replace(/\/+$/, "");
  }

  function buildIdleStatus(nextConfig = config) {
    if (nextConfig.transport === "server") {
      return {
        ready: false,
        status: "idle",
        device: "server",
        deviceLabel: "Localhost server",
        message: `Localhost server mode: ${nextConfig.serverUrl}`,
        error: null,
        transport: nextConfig.transport,
        serverUrl: nextConfig.serverUrl,
      };
    }

    return {
      ...LOCAL_STATUS,
      transport: nextConfig.transport,
      serverUrl: nextConfig.serverUrl,
    };
  }

  function sameConfig(snapshot) {
    return (
      snapshot.transport === config.transport &&
      snapshot.serverUrl === config.serverUrl
    );
  }

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
    const base = buildIdleStatus(config);
    status = {
      ...base,
      ...status,
      ...partial,
      transport: config.transport,
      serverUrl: config.serverUrl,
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
              if (config.transport === "local") {
                applyStatus(nextStatus);
              }
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

  async function requestBackground(action, payload = {}) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({ action, ...payload }, (response) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
          return;
        }
        resolve(response);
      });
    });
  }

  function decodeBase64ToArrayBuffer(base64) {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
  }

  function configure(nextConfig = {}) {
    const updated = {
      transport: normalizeTransport(nextConfig.transport ?? config.transport),
      serverUrl: normalizeServerUrl(nextConfig.serverUrl ?? config.serverUrl),
    };

    if (
      updated.transport === config.transport &&
      updated.serverUrl === config.serverUrl
    ) {
      return getStatus();
    }

    cancelPending();
    initPromise = null;
    config = updated;
    status = buildIdleStatus(config);
    emitStatus();
    return getStatus();
  }

  async function initializeLocal(snapshot) {
    if (status.ready && config.transport === "local") {
      return getStatus();
    }

    applyStatus({
      ready: false,
      status: "loading",
      device: "uninitialized",
      deviceLabel: "On-device",
      message: "Preparing on-device Kokoro...",
      error: null,
    });

    const pendingInit = getRuntime()
      .then((runtime) => runtime.initialize())
      .then((data) => {
        if (!sameConfig(snapshot) || config.transport !== "local") {
          return getStatus();
        }
        applyStatus({
          ...data,
          ready: true,
          status: "ready",
          deviceLabel: data?.deviceLabel || "On-device",
          error: null,
          message: data?.message || "On-device Kokoro ready",
        });
        return getStatus();
      })
      .catch((error) => {
        if (sameConfig(snapshot) && config.transport === "local") {
          applyStatus({
            ready: false,
            status: "error",
            message: error.message,
            error: error.message,
          });
        }
        throw error;
      })
      .finally(() => {
        if (initPromise === pendingInit) {
          initPromise = null;
        }
      });

    initPromise = pendingInit;
    return pendingInit;
  }

  async function requestServer(type, data = {}, snapshot = config) {
    const response = await requestBackground("serverTtsRequest", {
      type,
      data,
      serverUrl: snapshot.serverUrl,
    });

    if (!response?.ok) {
      throw new Error(response?.error || "Localhost Kokoro request failed");
    }

    return response.data;
  }

  async function initializeServer(snapshot) {
    applyStatus({
      ready: false,
      status: "loading",
      device: "server",
      deviceLabel: "Localhost server",
      message: `Checking localhost server at ${snapshot.serverUrl}...`,
      error: null,
    });

    const pendingInit = requestServer("health", {}, snapshot)
      .then((health) => {
        if (!sameConfig(snapshot) || config.transport !== "server") {
          return getStatus();
        }
        const device = health?.device || "server";
        applyStatus({
          ready: true,
          status: "ready",
          device: "server",
          deviceLabel: "Localhost server",
          message: `Using localhost server at ${snapshot.serverUrl} (${device})`,
          error: null,
        });
        return getStatus();
      })
      .catch((error) => {
        if (sameConfig(snapshot) && config.transport === "server") {
          applyStatus({
            ready: false,
            status: "error",
            device: "server",
            deviceLabel: "Localhost server",
            message: error.message,
            error: error.message,
          });
        }
        throw error;
      })
      .finally(() => {
        if (initPromise === pendingInit) {
          initPromise = null;
        }
      });

    initPromise = pendingInit;
    return pendingInit;
  }

  async function initialize() {
    if (initPromise) return initPromise;

    const snapshot = { ...config };
    if (snapshot.transport === "server") {
      return initializeServer(snapshot);
    }

    return initializeLocal(snapshot);
  }

  async function synthesize(text, options = {}) {
    const cleanText = (text || "").trim();
    if (!cleanText) {
      throw new Error("Empty text");
    }

    const snapshot = { ...config };
    await initialize();

    if (snapshot.transport === "server") {
      const data = await requestServer(
        "synthesize",
        {
          text: cleanText,
          voice: options.voice || "af_heart",
        },
        snapshot
      );

      return {
        audio: decodeBase64ToArrayBuffer(data.audio_b64),
        words: data.words || [],
        duration_ms: data.duration_ms || 0,
      };
    }

    const runtime = await getRuntime();
    return runtime.synthesize(cleanText, options.voice || "af_heart");
  }

  function cancelPending() {
    requestBackground("cancelServerTts").catch(() => {});
    if (runtimePromise) {
      runtimePromise
        .then((runtime) => runtime.cancelAll())
        .catch(() => {});
    }
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
    configure,
    initialize,
    synthesize,
    cancelPending,
    getStatus,
    setOnStatusChange,
  };
})();
