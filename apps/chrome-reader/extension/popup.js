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
  const engineStatus = document.getElementById("engine-status");
  const engineText = document.getElementById("engine-text");
  const selMode = document.getElementById("sel-mode");
  const selTransport = document.getElementById("sel-transport");
  const serverUrlSection = document.getElementById("server-url-section");
  const inputServerUrl = document.getElementById("input-server-url");
  const selVoice = document.getElementById("sel-voice");
  const sliderSpeed = document.getElementById("slider-speed");
  const speedValue = document.getElementById("speed-value");
  const optSkipCode = document.getElementById("opt-skip-code");
  const optAutoScroll = document.getElementById("opt-auto-scroll");
  const optHighlight = document.getElementById("opt-highlight");

  let currentTab = null;
  let pollInterval = null;
  let currentSettings = null;

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
          files: ["extractor.js", "highlighter.js", "tts-engine.js", "player.js", "content.js"],
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

  function normalizeServerUrl(serverUrl) {
    return (serverUrl || "http://localhost:8008").trim().replace(/\/+$/, "");
  }

  function applyTransportUi(transport = selTransport.value) {
    const isServer = transport === "server";
    serverUrlSection.style.display = isServer ? "" : "none";
  }

  // --- Save settings ---
  async function saveSettings() {
    const settings = {
      voice: selVoice.value,
      speed: parseFloat(sliderSpeed.value),
      mode: selMode.value,
      transport: selTransport.value,
      serverUrl: normalizeServerUrl(inputServerUrl.value),
      skipCode: optSkipCode.checked,
      autoScroll: optAutoScroll.checked,
      highlightWords: optHighlight.checked,
    };
    return new Promise((resolve) => {
      chrome.runtime.sendMessage({ action: "saveSettings", settings }, (response) => {
        currentSettings = response?.settings || settings;
        resolve(currentSettings);
      });
    });
  }

  function updateEngineStatus(engine) {
    const transport = engine?.transport || currentSettings?.transport || selTransport.value || "local";
    const serverUrl =
      engine?.serverUrl || currentSettings?.serverUrl || normalizeServerUrl(inputServerUrl.value);

    if (!engine) {
      engineStatus.className = "cr-status";
      if (transport === "server") {
        engineStatus.title = `Localhost server at ${serverUrl}`;
        engineText.textContent = `Localhost server mode: ${serverUrl}`;
      } else {
        engineStatus.title = "On-device Kokoro loads on first play";
        engineText.textContent = "On-device Kokoro loads on first play";
      }
      return;
    }

    if (engine.status === "ready" && engine.ready) {
      engineStatus.className = "cr-status connected";
      engineStatus.title = engine.message || `Running on ${engine.deviceLabel || "Kokoro"}`;
      engineText.textContent = engine.message || `Using ${engine.deviceLabel || "Kokoro"}`;
      return;
    }

    if (engine.status === "loading") {
      engineStatus.className = "cr-status loading";
      engineStatus.title = engine.message || "Preparing Kokoro";
      engineText.textContent = engine.message || "Preparing Kokoro";
      return;
    }

    if (engine.status === "error") {
      engineStatus.className = "cr-status disconnected";
      engineStatus.title = engine.error || engine.message || "Kokoro failed to initialize";
      engineText.textContent = engine.error || engine.message || "Kokoro failed to initialize";
      return;
    }

    engineStatus.className = "cr-status";
    if (transport === "server") {
      engineStatus.title = engine.message || `Localhost server at ${serverUrl}`;
      engineText.textContent = engine.message || `Localhost server mode: ${serverUrl}`;
    } else {
      engineStatus.title = engine.message || "On-device Kokoro loads on first play";
      engineText.textContent = engine.message || "On-device Kokoro loads on first play";
    }
  }

  // --- Update UI from state ---
  function updateUI(state) {
    updateEngineStatus(state?.engine);
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
      const settings = await saveSettings();
      progressText.textContent =
        settings.transport === "server"
          ? "Connecting to localhost Kokoro..."
          : "Starting on-device Kokoro...";
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
  selTransport.addEventListener("change", async () => {
    applyTransportUi();
    const settings = await saveSettings();
    updateEngineStatus(null);
    sendToContent({
      action: "updateSettings",
      settings: {
        transport: settings.transport,
        serverUrl: settings.serverUrl,
      },
    });
  });
  inputServerUrl.addEventListener("change", async () => {
    inputServerUrl.value = normalizeServerUrl(inputServerUrl.value);
    const settings = await saveSettings();
    updateEngineStatus(null);
    sendToContent({
      action: "updateSettings",
      settings: {
        transport: settings.transport,
        serverUrl: settings.serverUrl,
      },
    });
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
  currentSettings = settings;

  // Apply settings to UI
  selMode.value = settings.mode || "smart";
  selTransport.value = settings.transport || "local";
  inputServerUrl.value = normalizeServerUrl(settings.serverUrl);
  selVoice.value = settings.voice || "af_heart";
  sliderSpeed.value = settings.speed || 1.0;
  speedValue.textContent = `${parseFloat(sliderSpeed.value).toFixed(parseFloat(sliderSpeed.value) % 1 === 0 ? 0 : 1)}x`;
  optSkipCode.checked = settings.skipCode !== false;
  optAutoScroll.checked = settings.autoScroll !== false;
  optHighlight.checked = settings.highlightWords !== false;
  applyTransportUi();

  // Get initial state from content script
  const state = await sendToContent({ action: "getState" });
  updateUI(state);

  // Start polling for state updates
  startPolling();
})();
