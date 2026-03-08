const PORT_NAME = "chrome-reader-offscreen";

const DEFAULT_STATUS = {
  ready: false,
  status: "idle",
  device: "uninitialized",
  deviceLabel: "Not loaded",
  message: "Local Kokoro loads on first play",
  error: null,
};

let worker = null;
let nextRequestId = 1;
let initPromise = null;
let status = { ...DEFAULT_STATUS };
const pending = new Map();

function updateStatus(partial = {}) {
  status = {
    ...status,
    ...partial,
    error:
      partial.status === "error"
        ? partial.error || partial.message || status.error
        : partial.error ?? null,
  };
}

function getStatus() {
  return { ...status };
}

function terminateWorker() {
  if (!worker) return;
  worker.removeEventListener("message", handleWorkerMessage);
  worker.removeEventListener("error", handleWorkerError);
  worker.terminate();
  worker = null;
}

function rejectPending(message, predicate = () => true) {
  for (const [id, entry] of pending.entries()) {
    if (!predicate(entry)) continue;
    pending.delete(id);
    entry.reject(new Error(message));
  }
}

function handleWorkerError(event) {
  const message =
    event?.message ||
    event?.error?.message ||
    "Local Kokoro worker crashed";

  updateStatus({
    ready: false,
    status: "error",
    message,
    error: message,
  });
  rejectPending(message);
  initPromise = null;
  terminateWorker();
}

function handleWorkerMessage(event) {
  const msg = event?.data || {};

  if (msg.type === "status") {
    updateStatus(msg.data || {});
    return;
  }

  const request = pending.get(msg.id);
  if (!request) return;
  pending.delete(msg.id);

  if (msg.type === "initResult" || msg.type === "synthesizeResult") {
    request.resolve(msg.data);
    return;
  }

  const error = new Error(msg.error || "Local TTS worker request failed");
  if (request.type === "init") {
    updateStatus({
      ready: false,
      status: "error",
      message: error.message,
      error: error.message,
    });
  }
  request.reject(error);
}

function ensureWorker() {
  if (worker) return worker;

  try {
    worker = new Worker(chrome.runtime.getURL("tts-worker.mjs"), {
      type: "module",
      name: "chrome-reader-kokoro",
    });
  } catch (error) {
    const message = error?.message || "Failed to start local Kokoro worker";
    updateStatus({
      ready: false,
      status: "error",
      message,
      error: message,
    });
    throw new Error(message);
  }

  worker.addEventListener("message", handleWorkerMessage);
  worker.addEventListener("error", handleWorkerError);
  return worker;
}

function sendWorkerRequest(type, data = {}) {
  const currentWorker = ensureWorker();
  return new Promise((resolve, reject) => {
    const id = nextRequestId++;
    pending.set(id, { resolve, reject, type });
    currentWorker.postMessage({ id, type, data });
  });
}

async function initialize() {
  if (status.ready) return getStatus();
  if (initPromise) return initPromise;

  updateStatus({
    ready: false,
    status: "loading",
    message: "Preparing local Kokoro engine...",
    error: null,
  });

  initPromise = sendWorkerRequest("init")
    .then((data) => {
      updateStatus({
        ...data,
        ready: true,
        status: "ready",
        error: null,
        message: data?.message || "Local Kokoro ready",
      });
      return getStatus();
    })
    .catch((error) => {
      updateStatus({
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

async function synthesize(text, voice) {
  const cleanText = (text || "").trim();
  if (!cleanText) {
    throw new Error("Empty text");
  }

  await initialize();
  return sendWorkerRequest("synthesize", {
    text: cleanText,
    voice: voice || "af_heart",
  });
}

function cancelAll() {
  if (!worker) return;
  worker.postMessage({ type: "cancelAll" });
  rejectPending("Synthesis cancelled", (entry) => entry.type === "synthesize");
}

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunkSize = 0x8000;

  for (let i = 0; i < bytes.length; i += chunkSize) {
    const chunk = bytes.subarray(i, i + chunkSize);
    binary += String.fromCharCode(...chunk);
  }

  return btoa(binary);
}

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== PORT_NAME) return;

  port.onMessage.addListener(async (msg) => {
    const requestId = msg?.requestId;
    const type = msg?.type;
    const data = msg?.data || {};

    try {
      switch (type) {
        case "getStatus":
          port.postMessage({
            requestId,
            ok: true,
            status: getStatus(),
          });
          return;

        case "init":
          port.postMessage({
            requestId,
            ok: true,
            status: await initialize(),
          });
          return;

        case "synthesize": {
          const result = await synthesize(data.text, data.voice);
          const { audio, ...rest } = result;
          port.postMessage({
            requestId,
            ok: true,
            status: getStatus(),
            data: {
              ...rest,
              audioBase64: arrayBufferToBase64(audio),
            },
          });
          return;
        }

        case "cancelAll":
          cancelAll();
          port.postMessage({
            requestId,
            ok: true,
            status: getStatus(),
            data: { cancelled: true },
          });
          return;

        default:
          throw new Error(`Unknown offscreen TTS request "${type}"`);
      }
    } catch (error) {
      port.postMessage({
        requestId,
        ok: false,
        status: getStatus(),
        error: error?.message || String(error) || "Unknown offscreen TTS error",
      });
    }
  });
});
