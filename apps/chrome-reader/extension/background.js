/**
 * Chrome Reader - Background Service Worker
 * Handles keyboard shortcuts, persistent settings, and the offscreen TTS runtime.
 */

const DEFAULT_SETTINGS = {
  voice: "af_heart",
  speed: 1.0,
  mode: "smart",
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
      sendResponse(result.settings || DEFAULT_SETTINGS);
    });
    return true;
  }

  if (msg.action === "saveSettings") {
    chrome.storage.local.set({ settings: msg.settings }, () => {
      sendResponse({ ok: true });
    });
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
    if (!result.settings) {
      chrome.storage.local.set({ settings: DEFAULT_SETTINGS });
    }
  });
});
