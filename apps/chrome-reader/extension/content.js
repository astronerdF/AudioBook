/**
 * Chrome Reader - Content Script Coordinator
 * Ties together Extractor, Highlighter, and Player modules.
 * Handles communication with popup and background, and in-page controls.
 */

window.ChromeReader = window.ChromeReader || {};

ChromeReader.Controller = (() => {
  let controlsBar = null;
  let settings = null;
  let initialized = false;

  /**
   * Load settings from background.
   */
  async function loadSettings() {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage({ action: "getSettings" }, (s) => {
        settings = s || {
          serverUrl: "http://localhost:8008",
          voice: "af_heart",
          speed: 1.0,
          mode: "smart",
          skipCode: true,
          autoScroll: true,
          highlightWords: true,
        };
        resolve(settings);
      });
    });
  }

  /**
   * Create the floating controls bar on the page.
   */
  function createControlsBar() {
    if (controlsBar) return;

    controlsBar = document.createElement("div");
    controlsBar.id = "cr-controls-bar";
    controlsBar.classList.add("cr-hidden");
    controlsBar.innerHTML = `
      <button id="cr-btn-prev" title="Previous (Alt+Left)">&#9198;</button>
      <button id="cr-btn-play" title="Play/Pause (Alt+R)">&#9654;</button>
      <button id="cr-btn-next" title="Next (Alt+Right)">&#9197;</button>
      <button id="cr-btn-stop" title="Stop (Alt+S)">&#9724;</button>
      <span class="cr-progress-text" id="cr-progress">0 / 0</span>
    `;
    document.body.appendChild(controlsBar);

    // Event listeners
    document.getElementById("cr-btn-play").addEventListener("click", () => {
      ChromeReader.Player.toggle();
    });
    document.getElementById("cr-btn-stop").addEventListener("click", () => {
      stopReading();
    });
    document.getElementById("cr-btn-next").addEventListener("click", () => {
      ChromeReader.Player.skipForward();
    });
    document.getElementById("cr-btn-prev").addEventListener("click", () => {
      ChromeReader.Player.skipBack();
    });
  }

  function showControls() {
    if (controlsBar) controlsBar.classList.remove("cr-hidden");
  }

  function hideControls() {
    if (controlsBar) controlsBar.classList.add("cr-hidden");
  }

  function updateControls(state) {
    if (!controlsBar) return;
    const playBtn = document.getElementById("cr-btn-play");
    const progress = document.getElementById("cr-progress");

    if (playBtn) {
      playBtn.innerHTML = state.isPaused ? "&#9654;" : "&#10074;&#10074;";
    }
    if (progress) {
      progress.textContent = `${state.currentParaIdx + 1} / ${state.totalParagraphs}`;
    }
  }

  /**
   * Start reading the page.
   */
  async function startReading(mode) {
    if (!settings) await loadSettings();

    showStatus("Extracting content...", "loading");

    const readMode = mode || settings.mode || "smart";
    const paragraphs = ChromeReader.Extractor.extract(readMode, {
      skipCode: settings.skipCode,
    });

    if (!paragraphs || paragraphs.length === 0) {
      showStatus("No readable content found on this page.", "error");
      setTimeout(() => hideStatus(), 5000);
      return;
    }

    showStatus(
      `Found ${paragraphs.length} paragraphs. Connecting to ${settings.serverUrl}...`,
      "loading"
    );

    ChromeReader.Highlighter.setEnabled(settings.highlightWords !== false);
    ChromeReader.Highlighter.setAutoScroll(settings.autoScroll !== false);

    ChromeReader.Player.setOnError((errMsg) => {
      showStatus(errMsg, "error");
      setTimeout(() => hideStatus(), 5000);
    });

    ChromeReader.Player.setOnStatusUpdate((msg) => {
      showStatus(msg, "loading");
    });

    ChromeReader.Player.setOnStateChange((state) => {
      updateControls(state);
      try {
        chrome.runtime.sendMessage({ action: "stateUpdate", state });
      } catch (_) {}

      if (state.isPlaying && !state.isPaused) {
        showStatus(
          `Reading paragraph ${state.currentParaIdx + 1} / ${state.totalParagraphs}`,
          "success"
        );
      } else if (state.isPaused) {
        showStatus("Paused", "info");
      } else if (!state.isPlaying) {
        hideStatus();
        hideControls();
        ChromeReader.Highlighter.destroy();
      }
    });

    createControlsBar();
    showControls();

    ChromeReader.Player.start(paragraphs, {
      serverUrl: settings.serverUrl,
      voice: settings.voice,
      speed: settings.speed,
    });
  }

  function stopReading() {
    ChromeReader.Player.stop();
    hideControls();
    ChromeReader.Highlighter.destroy();
  }

  /**
   * Persistent status banner at top of page. Shows what Chrome Reader is doing.
   */
  let statusBanner = null;

  function showStatus(message, type = "info") {
    if (!statusBanner) {
      statusBanner = document.createElement("div");
      statusBanner.id = "cr-status-banner";
      document.body.appendChild(statusBanner);
    }
    const colors = {
      info: "background: #1a1a2e; color: #90caf9;",
      loading: "background: #1a1a2e; color: #ffd54f;",
      error: "background: #2e1a1a; color: #ef9a9a;",
      success: "background: #1a2e1a; color: #a5d6a7;",
    };
    statusBanner.style.cssText = `
      position: fixed; top: 0; left: 0; right: 0; z-index: 2147483647;
      ${colors[type] || colors.info}
      padding: 8px 20px; font-family: -apple-system, sans-serif;
      font-size: 13px; text-align: center;
      box-shadow: 0 2px 8px rgba(0,0,0,0.3);
      transition: opacity 0.3s;
    `;
    statusBanner.textContent = message;
    statusBanner.style.display = "block";
    statusBanner.style.opacity = "1";
  }

  function hideStatus() {
    if (statusBanner) {
      statusBanner.style.opacity = "0";
      setTimeout(() => {
        if (statusBanner) statusBanner.style.display = "none";
      }, 300);
    }
  }

  /**
   * Show a brief notification overlay (for errors/warnings that auto-dismiss).
   */
  function showNotification(message) {
    showStatus(message, "error");
    setTimeout(() => hideStatus(), 5000);
  }

  /**
   * Initialize message listener for popup/background communication.
   */
  function init() {
    if (initialized) return;
    initialized = true;

    chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
      switch (msg.action) {
        case "start":
          loadSettings().then((s) => {
            if (msg.mode) s.mode = msg.mode;
            if (msg.voice) s.voice = msg.voice;
            if (msg.speed) s.speed = msg.speed;
            settings = s;
            startReading(msg.mode);
          });
          sendResponse({ ok: true });
          return true;

        case "stop":
          stopReading();
          sendResponse({ ok: true });
          return true;

        case "toggle":
          if (ChromeReader.Player.isActive()) {
            ChromeReader.Player.toggle();
          } else {
            startReading();
          }
          sendResponse({ ok: true });
          return true;

        case "pause":
          ChromeReader.Player.pause();
          sendResponse({ ok: true });
          return true;

        case "resume":
          ChromeReader.Player.resume();
          sendResponse({ ok: true });
          return true;

        case "skipForward":
          ChromeReader.Player.skipForward();
          sendResponse({ ok: true });
          return true;

        case "skipBack":
          ChromeReader.Player.skipBack();
          sendResponse({ ok: true });
          return true;

        case "setSpeed":
          ChromeReader.Player.setSpeed(msg.speed);
          sendResponse({ ok: true });
          return true;

        case "setVoice":
          ChromeReader.Player.setVoice(msg.voice);
          sendResponse({ ok: true });
          return true;

        case "updateSettings":
          settings = { ...settings, ...msg.settings };
          if (msg.settings.highlightWords !== undefined) {
            ChromeReader.Highlighter.setEnabled(msg.settings.highlightWords);
          }
          if (msg.settings.autoScroll !== undefined) {
            ChromeReader.Highlighter.setAutoScroll(msg.settings.autoScroll);
          }
          sendResponse({ ok: true });
          return true;

        case "getState":
          sendResponse(ChromeReader.Player.getState());
          return true;

        default:
          sendResponse({ ok: false, error: "unknown action" });
          return true;
      }
    });
  }

  // Auto-initialize
  init();

  return { startReading, stopReading, init };
})();
