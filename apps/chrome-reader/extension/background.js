/**
 * Chrome Reader - Background Service Worker
 * Handles keyboard shortcuts, settings, and TTS server health checks.
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

// Keyboard shortcuts
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
    // Content script not loaded on this page
  }
});

// Settings management
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
    const url = msg.serverUrl || DEFAULT_SETTINGS.serverUrl;
    fetch(`${url}/health`, { signal: AbortSignal.timeout(3000) })
      .then((r) => r.json())
      .then((data) => sendResponse({ connected: true, ...data }))
      .catch(() => sendResponse({ connected: false }));
    return true;
  }
});

// Extension install - set defaults
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get("settings", (result) => {
    if (!result.settings) {
      chrome.storage.local.set({ settings: DEFAULT_SETTINGS });
    }
  });
});
