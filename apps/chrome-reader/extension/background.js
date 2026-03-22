/**
 * Chrome Reader - Background Service Worker
 * Handles keyboard shortcuts, persistent settings, and the offscreen TTS runtime.
 */

const DEFAULT_SETTINGS = {
  voice: "af_heart",
  speed: 1.0,
  mode: "smart",
  transport: "local",
  serverUrl: "http://localhost:8008",
  skipCode: true,
  autoScroll: true,
  highlightWords: true,
};

const OFFSCREEN_DOCUMENT_PATH = "offscreen.html";
const OFFSCREEN_PORT_NAME = "chrome-reader-offscreen";

let creatingOffscreen = null;
let connectingOffscreenPort = null;
let offscreenPort = null;
let nextOffscreenRequestId = 1;
const pendingOffscreenRequests = new Map();
let nextServerRequestId = 1;
const pendingServerRequests = new Map();

function mergeSettings(settings = {}) {
  return {
    ...DEFAULT_SETTINGS,
    ...settings,
  };
}

function normalizeServerUrl(serverUrl) {
  return (serverUrl || DEFAULT_SETTINGS.serverUrl).trim().replace(/\/+$/, "");
}

function validateServerUrl(serverUrl) {
  let parsed;
  try {
    parsed = new URL(serverUrl);
  } catch (_) {
    throw new Error("Server URL must be a valid http://localhost address");
  }

  const isSupportedHost =
    parsed.protocol === "http:" &&
    (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1");

  if (!isSupportedHost) {
    throw new Error("Server mode only supports http://localhost or http://127.0.0.1");
  }

  return parsed.toString().replace(/\/+$/, "");
}

async function parseServerResponse(response) {
  const contentType = response.headers.get("content-type") || "";

  if (contentType.includes("application/json")) {
    return response.json();
  }

  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch (_) {
    return { detail: text };
  }
}

async function requestServer(type, data = {}, serverUrl = DEFAULT_SETTINGS.serverUrl) {
  const baseUrl = validateServerUrl(normalizeServerUrl(serverUrl));
  let path = "";
  let init = {
    method: "GET",
    cache: "no-store",
  };

  if (type === "health") {
    path = "/health";
  } else if (type === "synthesize") {
    path = "/synthesize";
    init = {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        text: (data.text || "").trim(),
        voice: data.voice || DEFAULT_SETTINGS.voice,
      }),
    };
  } else {
    throw new Error(`Unsupported server request type "${type}"`);
  }

  const controller = new AbortController();
  const requestId = nextServerRequestId++;
  pendingServerRequests.set(requestId, controller);

  try {
    const response = await fetch(`${baseUrl}${path}`, {
      ...init,
      signal: controller.signal,
    });
    const payload = await parseServerResponse(response);

    if (!response.ok) {
      throw new Error(payload?.detail || payload?.error || `Server returned ${response.status}`);
    }

    return payload;
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error("Server request cancelled");
    }
    throw error;
  } finally {
    pendingServerRequests.delete(requestId);
  }
}

function cancelServerRequests() {
  for (const controller of pendingServerRequests.values()) {
    try {
      controller.abort();
    } catch (_) {}
  }
  pendingServerRequests.clear();
}

async function hasOffscreenDocument() {
  const offscreenUrl = chrome.runtime.getURL(OFFSCREEN_DOCUMENT_PATH);

  if (chrome.runtime.getContexts) {
    const contexts = await chrome.runtime.getContexts({
      contextTypes: ["OFFSCREEN_DOCUMENT"],
      documentUrls: [offscreenUrl],
    });
    return contexts.length > 0;
  }

  if (self.clients?.matchAll) {
    const clients = await self.clients.matchAll();
    return clients.some((client) => client.url === offscreenUrl);
  }

  return false;
}

async function ensureOffscreenDocument() {
  if (await hasOffscreenDocument()) return;
  if (creatingOffscreen) {
    await creatingOffscreen;
    return;
  }

  creatingOffscreen = chrome.offscreen.createDocument({
    url: OFFSCREEN_DOCUMENT_PATH,
    reasons: ["WORKERS"],
    justification: "Run the packaged Kokoro TTS worker outside page CSP restrictions.",
  });

  try {
    await creatingOffscreen;
  } finally {
    creatingOffscreen = null;
  }
}

function rejectPendingOffscreenRequests(message) {
  for (const [requestId, entry] of pendingOffscreenRequests.entries()) {
    pendingOffscreenRequests.delete(requestId);
    entry.reject(new Error(message));
  }
}

function attachOffscreenPort(port) {
  offscreenPort = port;

  port.onMessage.addListener((message) => {
    const requestId = message?.requestId;
    if (!requestId) return;

    const pending = pendingOffscreenRequests.get(requestId);
    if (!pending) return;

    pendingOffscreenRequests.delete(requestId);
    pending.resolve(message);
  });

  port.onDisconnect.addListener(() => {
    if (offscreenPort === port) {
      offscreenPort = null;
    }
    rejectPendingOffscreenRequests("Local Kokoro runtime disconnected");
  });
}

async function ensureOffscreenPort() {
  if (offscreenPort) return offscreenPort;
  if (connectingOffscreenPort) return connectingOffscreenPort;

  connectingOffscreenPort = (async () => {
    await ensureOffscreenDocument();
    const port = chrome.runtime.connect({ name: OFFSCREEN_PORT_NAME });
    attachOffscreenPort(port);
    return port;
  })();

  try {
    return await connectingOffscreenPort;
  } finally {
    connectingOffscreenPort = null;
  }
}

async function requestOffscreen(type, data = {}) {
  const port = await ensureOffscreenPort();

  return new Promise((resolve, reject) => {
    const requestId = nextOffscreenRequestId++;
    pendingOffscreenRequests.set(requestId, { resolve, reject });

    try {
      port.postMessage({ requestId, type, data });
    } catch (error) {
      pendingOffscreenRequests.delete(requestId);
      reject(error);
    }
  });
}

chrome.commands.onCommand.addListener(async (command) => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) return;

  try {
    if (command === "toggle-reading") {
      chrome.tabs.sendMessage(tab.id, { action: "toggle" });
    } else if (command === "stop-reading") {
      chrome.tabs.sendMessage(tab.id, { action: "stop" });
    }
  } catch (_) {
    // Content script is not available on this page.
  }
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.action === "getSettings") {
    chrome.storage.local.get("settings", (result) => {
      sendResponse(mergeSettings(result.settings));
    });
    return true;
  }

  if (msg.action === "saveSettings") {
    chrome.storage.local.get("settings", (result) => {
      const settings = mergeSettings({
        ...result.settings,
        ...msg.settings,
      });
      chrome.storage.local.set({ settings }, () => {
        sendResponse({ ok: true, settings });
      });
    });
    return true;
  }

  if (msg.action === "serverTtsRequest") {
    requestServer(msg.type, msg.data || {}, msg.serverUrl)
      .then((data) => {
        sendResponse({ ok: true, data });
      })
      .catch((error) => {
        sendResponse({
          ok: false,
          error: error?.message || String(error) || "Localhost Kokoro request failed",
        });
      });
    return true;
  }

  if (msg.action === "cancelServerTts") {
    cancelServerRequests();
    sendResponse({ ok: true });
    return true;
  }

  if (msg.action === "ttsRequest") {
    requestOffscreen(msg.type, msg.data || {})
      .then((response) => {
        sendResponse(response || { ok: false, error: "No response from local Kokoro runtime" });
      })
      .catch((error) => {
        sendResponse({
          ok: false,
          error: error?.message || String(error) || "Local Kokoro request failed",
        });
      });
    return true;
  }
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get("settings", (result) => {
    chrome.storage.local.set({ settings: mergeSettings(result.settings) });
  });
});
