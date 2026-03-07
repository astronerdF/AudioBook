/**
 * Chrome Reader - Smart Content Extractor
 * Extracts readable text from any webpage using a Readability-inspired algorithm.
 * Maps extracted words back to their DOM text nodes for highlighting.
 */

window.ChromeReader = window.ChromeReader || {};

ChromeReader.Extractor = (() => {
  // Elements to ignore entirely
  const SKIP_TAGS = new Set([
    "SCRIPT", "STYLE", "NOSCRIPT", "IFRAME", "OBJECT", "EMBED",
    "SVG", "CANVAS", "VIDEO", "AUDIO", "MAP", "TEMPLATE",
  ]);

  // Block elements that create paragraph boundaries
  const BLOCK_TAGS = new Set([
    "P", "DIV", "ARTICLE", "SECTION", "MAIN", "ASIDE", "HEADER",
    "FOOTER", "NAV", "BLOCKQUOTE", "PRE", "UL", "OL", "LI",
    "H1", "H2", "H3", "H4", "H5", "H6", "TABLE", "FIGURE",
    "FIGCAPTION", "DD", "DT", "ADDRESS", "DETAILS", "SUMMARY",
  ]);

  // Positive class/ID patterns (signal main content)
  const POSITIVE_RE = /article|post|content|entry|story|body|text|blog|main|page|prose|markdown|doc/i;
  // Negative class/ID patterns (signal non-content)
  const NEGATIVE_RE = /comment|sidebar|nav|menu|footer|header|widget|related|social|share|popup|modal|banner|promo|ad-|cookie|alert|notification|toolbar|tooltip|overlay|drawer/i;

  // Known site-specific selectors (tried first)
  const SITE_SELECTORS = [
    "article",                               // semantic HTML
    "[role='main'] article",
    "[role='article']",
    "main article",
    "main",
    ".post-content",                         // WordPress/blogs
    ".entry-content",
    ".article-body",
    ".article-content",
    ".story-body",
    "#article-body",
    ".markdown-body",                        // GitHub
    ".s-prose",                              // Stack Overflow
    "#mw-content-text",                      // Wikipedia
    ".caas-body",                            // Yahoo News
    '[data-testid="article-body"]',
    ".post-text",                            // Forums
    ".comment-content",
  ];

  /**
   * Score a DOM element for content likelihood.
   */
  function scoreElement(el) {
    if (!(el instanceof HTMLElement)) return -Infinity;
    let score = 0;
    const tag = el.tagName;

    // Tag bonuses
    if (tag === "ARTICLE" || tag === "MAIN") score += 50;
    if (tag === "SECTION") score += 5;
    if (tag === "DIV") score += 5;
    if (["NAV", "ASIDE", "FOOTER", "HEADER", "FORM"].includes(tag)) score -= 30;

    // Class/ID analysis
    const classId = ((el.className || "") + " " + (el.id || "")).toString();
    if (POSITIVE_RE.test(classId)) score += 25;
    if (NEGATIVE_RE.test(classId)) score -= 25;

    // Text density
    const text = el.innerText || "";
    const html = el.innerHTML || "";
    if (html.length > 0) {
      score += (text.length / html.length) * 40;
    }

    // Paragraph density
    const pCount = el.querySelectorAll("p").length;
    score += Math.min(pCount * 3, 30);

    // Text length
    if (text.length > 500) score += 20;
    if (text.length > 2000) score += 10;
    if (text.length < 80) score -= 20;

    // Link density penalty
    const links = el.querySelectorAll("a");
    let linkTextLen = 0;
    links.forEach((a) => (linkTextLen += (a.innerText || "").length));
    if (text.length > 0) {
      score -= (linkTextLen / text.length) * 40;
    }

    return score;
  }

  /**
   * Find the best content root element.
   */
  function findContentRoot() {
    // Try site-specific selectors first
    for (const selector of SITE_SELECTORS) {
      try {
        const el = document.querySelector(selector);
        if (el && (el.innerText || "").trim().length > 100) {
          return el;
        }
      } catch (_) {
        // Invalid selector on this page
      }
    }

    // Score all candidate elements
    const candidates = document.querySelectorAll(
      "div, section, article, main, td"
    );
    let best = null;
    let bestScore = -Infinity;

    candidates.forEach((el) => {
      const s = scoreElement(el);
      if (s > bestScore) {
        bestScore = s;
        best = el;
      }
    });

    return best || document.body;
  }

  /**
   * Extract paragraphs from a root element.
   * Returns array of { element, text, textNodes: [{node, start, end}] }
   */
  function extractParagraphs(root, options = {}) {
    const skipCode = options.skipCode !== false;
    const paragraphs = [];

    function shouldSkip(el) {
      if (SKIP_TAGS.has(el.tagName)) return true;
      if (el.getAttribute("aria-hidden") === "true") return true;
      if (el.hidden) return true;
      const style = getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") return true;
      if (skipCode && (el.tagName === "PRE" || el.tagName === "CODE")) {
        // Skip code blocks but allow inline <code> (single line, short)
        if (el.tagName === "PRE") return true;
        if (el.tagName === "CODE" && el.parentElement?.tagName === "PRE") return true;
      }
      const classId = ((el.className || "") + " " + (el.id || "")).toString();
      if (NEGATIVE_RE.test(classId) && el !== root) return true;
      return false;
    }

    function walkBlock(blockEl) {
      const textNodes = [];
      let fullText = "";

      function collectText(node) {
        if (node.nodeType === Node.TEXT_NODE) {
          const val = node.nodeValue;
          if (val && val.trim()) {
            textNodes.push({
              node: node,
              start: fullText.length,
              end: fullText.length + val.length,
            });
            fullText += val;
          } else if (val && /\s/.test(val) && fullText.length > 0) {
            // Preserve whitespace between inline elements
            if (!fullText.endsWith(" ")) {
              fullText += " ";
            }
          }
          return;
        }
        if (node.nodeType !== Node.ELEMENT_NODE) return;
        if (shouldSkip(node)) return;

        // If this is a nested block element, flush current and recurse
        if (BLOCK_TAGS.has(node.tagName) && node !== blockEl) {
          if (fullText.trim()) {
            paragraphs.push({
              element: blockEl,
              text: fullText.trim(),
              textNodes: [...textNodes],
            });
            textNodes.length = 0;
            fullText = "";
          }
          walkBlock(node);
          return;
        }

        // Add space before inline elements if needed
        if (fullText.length > 0 && !fullText.endsWith(" ")) {
          const display = getComputedStyle(node).display;
          if (display === "inline-block" || display === "block") {
            fullText += " ";
          }
        }

        for (const child of node.childNodes) {
          collectText(child);
        }
      }

      for (const child of blockEl.childNodes) {
        collectText(child);
      }

      if (fullText.trim()) {
        paragraphs.push({
          element: blockEl,
          text: fullText.trim(),
          textNodes: [...textNodes],
        });
      }
    }

    // Walk top-level block children of the root
    const blocks = root.querySelectorAll(
      Array.from(BLOCK_TAGS).join(",")
    );

    if (blocks.length > 0) {
      // Use direct block children, avoid double-processing nested ones
      const processed = new Set();
      blocks.forEach((block) => {
        // Only process if not inside an already-processed block
        let dominated = false;
        for (const p of processed) {
          if (p.contains(block) && p !== block) {
            dominated = true;
            break;
          }
        }
        if (!dominated && !shouldSkip(block)) {
          walkBlock(block);
          processed.add(block);
        }
      });
    } else {
      // No block structure; treat root as single block
      walkBlock(root);
    }

    // Filter empty / very short paragraphs
    return paragraphs.filter((p) => p.text.length > 10);
  }

  /**
   * Get text from the user's current selection.
   */
  function extractSelection() {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) return null;

    const range = sel.getRangeAt(0);
    const text = sel.toString().trim();
    if (!text || text.length < 5) return null;

    // Get the common ancestor and collect text nodes in the range
    const container = range.commonAncestorContainer;
    const element =
      container.nodeType === Node.ELEMENT_NODE
        ? container
        : container.parentElement;

    // Build text node map from the selection range
    const textNodes = [];
    const walker = document.createTreeWalker(
      element,
      NodeFilter.SHOW_TEXT,
      null
    );
    let node;
    let offset = 0;
    while ((node = walker.nextNode())) {
      if (sel.containsNode(node, true)) {
        const val = node.nodeValue || "";
        textNodes.push({ node, start: offset, end: offset + val.length });
        offset += val.length;
      }
    }

    return [{ element, text, textNodes }];
  }

  /**
   * Extract text from the visible viewport area.
   */
  function extractVisible(root) {
    const all = extractParagraphs(root);
    const vh = window.innerHeight;
    return all.filter((p) => {
      const rect = p.element.getBoundingClientRect();
      return rect.bottom > 0 && rect.top < vh;
    });
  }

  /**
   * Extract only headings for a quick summary.
   */
  function extractHeadings(root) {
    const headings = root.querySelectorAll("h1, h2, h3, h4, h5, h6");
    const result = [];
    headings.forEach((h) => {
      const text = (h.innerText || "").trim();
      if (text.length > 2) {
        const textNodes = [];
        const walker = document.createTreeWalker(h, NodeFilter.SHOW_TEXT, null);
        let node;
        let offset = 0;
        while ((node = walker.nextNode())) {
          const val = node.nodeValue || "";
          textNodes.push({ node, start: offset, end: offset + val.length });
          offset += val.length;
        }
        result.push({ element: h, text, textNodes });
      }
    });
    return result;
  }

  /**
   * Main extraction entry point.
   * @param {string} mode - "smart" | "selection" | "visible" | "full" | "headings"
   * @param {object} options - { skipCode: bool }
   * @returns {Array} paragraphs with DOM mappings
   */
  function extract(mode = "smart", options = {}) {
    if (mode === "selection") {
      const sel = extractSelection();
      if (sel) return sel;
      // Fallback to smart if no selection
      mode = "smart";
    }

    const root =
      mode === "full" ? document.body : findContentRoot();

    if (mode === "headings") {
      return extractHeadings(root);
    }

    if (mode === "visible") {
      return extractVisible(root);
    }

    return extractParagraphs(root, options);
  }

  return { extract, findContentRoot, scoreElement };
})();
