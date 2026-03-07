/**
 * Chrome Reader - Background Service Worker
 * Handles keyboard shortcuts, settings, health checks, and TTS proxying.
 */

const DEFAULT_SETTINGS = {
  serverUrl: "http://localhost:8008",
  voice: "af_heart",
  speed: 1.0,
  mode: "smart",
  skipCode: true,
  autoScroll: true,
  highlightWords: true,
};

async function fetchWithTimeout(url, options = {}, timeoutMs = 30000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function parseErrorResponse(resp) {
  try {
    const body = await resp.json();
    return body?.detail || body?.message || `HTTP ${resp.status}`;
  } catch (_) {
    return `HTTP ${resp.status}`;
  }
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

  if (msg.action === "checkServer") {
    (async () => {
      const url = msg.serverUrl || DEFAULT_SETTINGS.serverUrl;
      try {
        const resp = await fetchWithTimeout(`${url}/health`, {}, 4000);
        if (!resp.ok) {
          sendResponse({ connected: false, error: await parseErrorResponse(resp) });
          return;
        }
        const data = await resp.json();
        sendResponse({ connected: true, ...data });
      } catch (err) {
        sendResponse({ connected: false, error: err?.message || "Health check failed" });
      }
    })();
    return true;
  }

  if (msg.action === "synthesize") {
    (async () => {
      const url = msg.serverUrl || DEFAULT_SETTINGS.serverUrl;
      const text = (msg.text || "").trim();
      const voice = msg.voice || DEFAULT_SETTINGS.voice;

      if (!text) {
        sendResponse({ ok: false, error: "Empty text" });
        return;
      }

      try {
        const resp = await fetchWithTimeout(
          `${url}/synthesize`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text, voice }),
          },
          45000
        );

        if (!resp.ok) {
          sendResponse({ ok: false, error: await parseErrorResponse(resp) });
          return;
        }

        const data = await resp.json();
        sendResponse({ ok: true, data });
      } catch (err) {
        sendResponse({
          ok: false,
          error: err?.name === "AbortError" ? "TTS request timed out" : (err?.message || "TTS request failed"),
        });
      }
    })();
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
