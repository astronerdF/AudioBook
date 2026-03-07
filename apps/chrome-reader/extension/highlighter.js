/**
 * Chrome Reader - Word Highlighter
 * Uses positioned overlay divs to highlight words without modifying page DOM.
 * Supports auto-scroll to follow the reading position.
 */

window.ChromeReader = window.ChromeReader || {};

ChromeReader.Highlighter = (() => {
  let container = null;
  let wordOverlay = null;
  let sentenceOverlay = null;
  let enabled = true;
  let autoScroll = true;

  function init() {
    if (container) return;
    container = document.createElement("div");
    container.id = "cr-highlight-container";
    document.body.appendChild(container);

    wordOverlay = document.createElement("div");
    wordOverlay.className = "cr-word-highlight";
    container.appendChild(wordOverlay);

    sentenceOverlay = document.createElement("div");
    sentenceOverlay.className = "cr-sentence-highlight";
    container.appendChild(sentenceOverlay);
  }

  function destroy() {
    if (container) {
      container.remove();
      container = null;
      wordOverlay = null;
      sentenceOverlay = null;
    }
  }

  /**
   * Find the text node and offset for a character position in a paragraph.
   * @param {Array} textNodes - [{node, start, end}] from extractor
   * @param {number} charPos - character position in the flat paragraph text
   * @returns {{node: Text, offset: number}|null}
   */
  function findTextNodeAt(textNodes, charPos) {
    for (const tn of textNodes) {
      if (charPos >= tn.start && charPos < tn.end) {
        return { node: tn.node, offset: charPos - tn.start };
      }
    }
    // If exact match not found, return closest
    if (textNodes.length > 0) {
      const last = textNodes[textNodes.length - 1];
      if (charPos >= last.end) {
        return {
          node: last.node,
          offset: Math.min(charPos - last.start, (last.node.nodeValue || "").length),
        };
      }
    }
    return null;
  }

  /**
   * Highlight a specific word using overlay positioning.
   * @param {Array} textNodes - paragraph text nodes from extractor
   * @param {object} wordInfo - {word, char_start, char_end} from TTS timing
   */
  function highlightWord(textNodes, wordInfo) {
    if (!enabled || !wordOverlay) return;
    init();

    const startPos = findTextNodeAt(textNodes, wordInfo.char_start);
    const endPos = findTextNodeAt(textNodes, wordInfo.char_end);
    if (!startPos || !endPos) {
      wordOverlay.style.display = "none";
      return;
    }

    try {
      const range = document.createRange();
      range.setStart(startPos.node, startPos.offset);
      range.setEnd(
        endPos.node,
        Math.min(endPos.offset, (endPos.node.nodeValue || "").length)
      );

      const rect = range.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) {
        wordOverlay.style.display = "none";
        return;
      }

      const scrollX = window.scrollX;
      const scrollY = window.scrollY;

      wordOverlay.style.left = `${rect.left + scrollX - 2}px`;
      wordOverlay.style.top = `${rect.top + scrollY - 1}px`;
      wordOverlay.style.width = `${rect.width + 4}px`;
      wordOverlay.style.height = `${rect.height + 2}px`;
      wordOverlay.style.display = "block";

      if (autoScroll) {
        scrollToWord(rect);
      }
    } catch (_) {
      wordOverlay.style.display = "none";
    }
  }

  /**
   * Highlight the element containing the current sentence.
   */
  function highlightSentenceElement(element) {
    if (!enabled || !sentenceOverlay) return;
    init();

    try {
      const rect = element.getBoundingClientRect();
      const scrollX = window.scrollX;
      const scrollY = window.scrollY;

      sentenceOverlay.style.left = `${rect.left + scrollX - 4}px`;
      sentenceOverlay.style.top = `${rect.top + scrollY - 2}px`;
      sentenceOverlay.style.width = `${rect.width + 8}px`;
      sentenceOverlay.style.height = `${rect.height + 4}px`;
      sentenceOverlay.style.display = "block";
    } catch (_) {
      sentenceOverlay.style.display = "none";
    }
  }

  /**
   * Smoothly scroll to keep the highlighted word visible.
   */
  function scrollToWord(rect) {
    const vh = window.innerHeight;
    const margin = vh * 0.3; // Keep word in the middle 40% of viewport

    if (rect.top < margin) {
      window.scrollBy({ top: rect.top - margin, behavior: "smooth" });
    } else if (rect.bottom > vh - margin) {
      window.scrollBy({
        top: rect.bottom - (vh - margin),
        behavior: "smooth",
      });
    }
  }

  function clearWord() {
    if (wordOverlay) wordOverlay.style.display = "none";
  }

  function clearAll() {
    if (wordOverlay) wordOverlay.style.display = "none";
    if (sentenceOverlay) sentenceOverlay.style.display = "none";
  }

  function setEnabled(val) {
    enabled = val;
    if (!val) clearAll();
  }

  function setAutoScroll(val) {
    autoScroll = val;
  }

  return {
    init,
    destroy,
    highlightWord,
    highlightSentenceElement,
    clearWord,
    clearAll,
    setEnabled,
    setAutoScroll,
  };
})();
