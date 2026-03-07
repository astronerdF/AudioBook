/**
 * Chrome Reader - Popup Controller
 * Manages the popup UI, communicates with content script and background.
 */

(async function () {
  // --- DOM refs ---
  const btnPlay = document.getElementById("btn-play");
  const btnStop = document.getElementById("btn-stop");
  const btnPrev = document.getElementById("btn-prev");
  const btnNext = document.getElementById("btn-next");
  const iconPlay = document.getElementById("icon-play");
  const iconPause = document.getElementById("icon-pause");
  const progressText = document.getElementById("progress-text");
  const serverStatus = document.getElementById("server-status");
  const selMode = document.getElementById("sel-mode");
  const selVoice = document.getElementById("sel-voice");
  const sliderSpeed = document.getElementById("slider-speed");
  const speedValue = document.getElementById("speed-value");
  const optSkipCode = document.getElementById("opt-skip-code");
  const optAutoScroll = document.getElementById("opt-auto-scroll");
  const optHighlight = document.getElementById("opt-highlight");
  const inputServer = document.getElementById("input-server");

  let currentTab = null;
  let pollInterval = null;

  // --- Get active tab ---
  async function getTab() {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    return tab;
  }

  // --- Ensure content scripts are injected ---
  async function ensureContentScript() {
    if (!currentTab?.id) return false;
    try {
      await chrome.tabs.sendMessage(currentTab.id, { action: "getState" });
      return true;
    } catch (_) {
      // Not loaded - inject dynamically
      try {
        await chrome.scripting.executeScript({
          target: { tabId: currentTab.id },
          files: ["extractor.js", "highlighter.js", "player.js", "content.js"],
        });
        await chrome.scripting.insertCSS({
          target: { tabId: currentTab.id },
          files: ["content.css"],
        });
        return true;
      } catch (e) {
        return false;
      }
    }
  }

  // --- Send message to content script ---
  async function sendToContent(msg) {
    if (!currentTab?.id) return null;
    try {
      return await chrome.tabs.sendMessage(currentTab.id, msg);
    } catch (_) {
      return null;
    }
  }

  // --- Load settings ---
  async function loadSettings() {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage({ action: "getSettings" }, (s) => {
        resolve(s || {});
      });
    });
  }

  // --- Save settings ---
  async function saveSettings() {
    const settings = {
      serverUrl: inputServer.value.trim() || "http://localhost:8008",
      voice: selVoice.value,
      speed: parseFloat(sliderSpeed.value),
      mode: selMode.value,
      skipCode: optSkipCode.checked,
      autoScroll: optAutoScroll.checked,
      highlightWords: optHighlight.checked,
    };
    chrome.runtime.sendMessage({ action: "saveSettings", settings });
    return settings;
  }

  // --- Check server health ---
  async function checkServer() {
    const url = inputServer.value.trim() || "http://localhost:8008";
    chrome.runtime.sendMessage(
      { action: "checkServer", serverUrl: url },
      (resp) => {
        if (resp?.connected) {
          serverStatus.className = "cr-status connected";
          serverStatus.title = `Connected (${resp.device || "unknown device"})`;
        } else {
          serverStatus.className = "cr-status disconnected";
          serverStatus.title = "Cannot connect to TTS server";
        }
      }
    );
  }

  // --- Update UI from state ---
  function updateUI(state) {
    if (!state) return;

    if (state.isPlaying) {
      if (state.isPaused) {
        iconPlay.style.display = "";
        iconPause.style.display = "none";
        progressText.textContent = `Paused - ${state.currentParaIdx + 1} / ${state.totalParagraphs}`;
      } else {
        iconPlay.style.display = "none";
        iconPause.style.display = "";
        progressText.textContent = `Reading ${state.currentParaIdx + 1} / ${state.totalParagraphs}`;
      }
    } else {
      iconPlay.style.display = "";
      iconPause.style.display = "none";
      progressText.textContent = "Ready";
    }
  }

  // --- Poll content script for state ---
  function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(async () => {
      const state = await sendToContent({ action: "getState" });
      updateUI(state);
    }, 500);
  }

  // --- Event: Play/Pause ---
  btnPlay.addEventListener("click", async () => {
    progressText.textContent = "Injecting scripts...";
    const loaded = await ensureContentScript();
    if (!loaded) {
      progressText.textContent = "Cannot access this page";
      return;
    }

    const state = await sendToContent({ action: "getState" });
    if (state?.isPlaying) {
      sendToContent({ action: "toggle" });
    } else {
      progressText.textContent = "Starting...";
      const settings = await saveSettings();
      sendToContent({
        action: "start",
        mode: selMode.value,
        voice: selVoice.value,
        speed: parseFloat(sliderSpeed.value),
      });
    }
  });

  btnStop.addEventListener("click", () => sendToContent({ action: "stop" }));
  btnPrev.addEventListener("click", () => sendToContent({ action: "skipBack" }));
  btnNext.addEventListener("click", () => sendToContent({ action: "skipForward" }));

  // --- Speed slider ---
  sliderSpeed.addEventListener("input", () => {
    const val = parseFloat(sliderSpeed.value);
    speedValue.textContent = `${val.toFixed(val % 1 === 0 ? 0 : 1)}x`;
    sendToContent({ action: "setSpeed", speed: val });
    saveSettings();
  });

  // --- Voice change ---
  selVoice.addEventListener("change", () => {
    sendToContent({ action: "setVoice", voice: selVoice.value });
    saveSettings();
  });

  // --- Options ---
  optSkipCode.addEventListener("change", () => {
    saveSettings();
    sendToContent({ action: "updateSettings", settings: { skipCode: optSkipCode.checked } });
  });
  optAutoScroll.addEventListener("change", () => {
    saveSettings();
    sendToContent({ action: "updateSettings", settings: { autoScroll: optAutoScroll.checked } });
  });
  optHighlight.addEventListener("change", () => {
    saveSettings();
    sendToContent({ action: "updateSettings", settings: { highlightWords: optHighlight.checked } });
  });

  // --- Mode change ---
  selMode.addEventListener("change", saveSettings);

  // --- Server URL change ---
  let serverDebounce;
  inputServer.addEventListener("input", () => {
    clearTimeout(serverDebounce);
    serverDebounce = setTimeout(() => {
      saveSettings();
      checkServer();
    }, 500);
  });

  // --- Listen for state updates from content script ---
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.action === "stateUpdate") {
      updateUI(msg.state);
    }
  });

  // --- Initialize ---
  currentTab = await getTab();
  const settings = await loadSettings();

  // Apply settings to UI
  selMode.value = settings.mode || "smart";
  selVoice.value = settings.voice || "af_heart";
  sliderSpeed.value = settings.speed || 1.0;
  speedValue.textContent = `${parseFloat(sliderSpeed.value).toFixed(parseFloat(sliderSpeed.value) % 1 === 0 ? 0 : 1)}x`;
  optSkipCode.checked = settings.skipCode !== false;
  optAutoScroll.checked = settings.autoScroll !== false;
  optHighlight.checked = settings.highlightWords !== false;
  inputServer.value = settings.serverUrl || "http://localhost:8008";

  // Get initial state from content script
  const state = await sendToContent({ action: "getState" });
  updateUI(state);

  // Check server connection
  checkServer();

  // Start polling for state updates
  startPolling();
})();
